import requests
import json
import logging
import yaml
from base64 import b64decode as b64d
from github import Github, Repository, UnknownObjectException
from github.Team import Team
from github.NamedUser import NamedUser
from datetime import datetime
from typing import Tuple

class RepoCreateError(Exception):
    pass
class RepoModifyError(Exception):
    pass
class RepoExistsError(Exception):
    pass

class GitManager:
    DEFAULT_REVIEWER_COUNT = 1
    def __init__(self, gh_token: str, org: str):
        self._token = gh_token
       
        self._gh = Github(gh_token)
        self._org = self._gh.get_organization(org)
        self._headers = {
            "Authorization": f'token {self._token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        # for teams. These are initialized when called in get_teams
        self._last_teams_pull = None
        self._teams = None
        self._users = None
        self.get_teams()
        # public attrs
        self.visibilities = ['public', 'private', 'internal']
        # load the templates from the conf file which is expeted to be
        # in the same directory
        self._conf = None
        with open('./conf.yml') as conffile:
            try:
                self._conf = yaml.safe_load(conffile)
            except yaml.YAMLError as e:
                logging.fatal(f'Error loading config file. Error: {e}')

    def get_templates(self):
        return self._conf['github']['templates']

    def _make_repo_internal(self, repo: str):
        if type(repo) is Repository.Repository:
            repo = repo.full_name
        url = f'https://api.github.com/repos/{repo}'
        payload = {
            'visibility': 'internal'
        }
        resp = requests.patch(url, headers=self._headers, data=json.dumps(payload))
        if resp.status_code != 200:
            # TODO: log
            raise RepoModifyError

    def _create_repo_from_template(self, name: str, template: str, visibility: str, description: str='') -> Repository.Repository:
        if template == 'None':
            # TODO: log
            raise ValueError("None used for template")
        # set private to true if visibility is set to private or internal,
        # we have to adjust after creation because the API is behind
        visibility = visibility.lower()
        private = (visibility == "private" or visibility == "internal")
        # see: https://docs.github.com/en/rest/reference/repos#create-a-repository-using-a-template
        payload = {
            'name': name,
            'owner': self._org.login,
            'description': description,
            'private': private
        }
        url = f'https://api.github.com/repos/{template}/generate'
        resp = requests.post(url, headers=self._headers, data=json.dumps(payload))
        # TODO: handle resp code 422 (repo already exists)
        if resp.status_code != 201:
            # TODO: log
            raise RepoCreateError("failed to create a repo")
        body = resp.content.decode('utf-8')
        created_repo = json.loads(body)
        # adjust visibility:
        if visibility == 'internal':
            # TODO: wrap in try/except and return semi-error on failure
            self._make_repo_internal(created_repo['full_name'])
        # get and return the repo
        return self._org.get_repo(created_repo['name'])

    def _create_repo(self, name, visibility, description='') -> Repository.Repository:
        # check visibility:
        if visibility not in self.visibilities:
            raise ValueError("invalid argument for visibility")
        visibility = visibility.lower()
        # create the repo
        repo = self._org.create_repo(
            name=name,
            description=description,
            private=(visibility == 'private' or visibility == 'internal'),
            auto_init=True, # creates an empty README to make cloning easier
        )
        if visibility == 'internal':
            # TODO: handle soft fail
            self._make_repo_internal(repo)
        return repo

    def _check_repo_exists(self, name: str):
        # make sure the repo doesn't already exist
        try:
            check = self._org.get_repo(name)
            if check:
                return True
            return False
        except UnknownObjectException:
            return False
        except Exception as e:
            logging.error(f"Error getting repo. Name: {name}. Error: {e}")

    def _add_codeowners(self, team, repo: Repository.Repository):
        commit_message = 'CODEOWNERS by slack-gitbot'
        # team is a user, set the codeowners string
        codeowners = None
        co_team = None
        for user in self._users:
            if team.lower() == user.login.lower():
                codeowners = f'# added by slack-gitbot\n* @{user.login}'
                break
        # possibly overwrite the codeowners value if it also matches a team.
        # we should default to teams vs users
        for org_team in self._teams:
            if team.lower() == org_team.name.lower():
                codeowners = f'# added by slack-gitbot\n* @puppetlabs/{org_team.slug}'
                co_team = org_team
                break
        if not codeowners:
            logging.error(f"couldn't find a team or user for the codeowners: {team}")
            raise ValueError("couldn't find team or user for codeowners!")
        # Write the codeowners file
        c = None
        try:
            c = repo.get_contents('CODEOWNERS')
        except UnknownObjectException:
            logging.debug(f"no codeowners in repo: {repo}, going to create one")
            pass
        except Exception as e:
            logging.error(f'uncaught error in add codeowners. {e}')
            raise e
        if c:
            ccontents = b64d(c.content).decode('utf-8')
            content = f'{ccontents}\n{codeowners}'
            repo.update_file('CODEOWNERS', commit_message, content, c.sha)
        else:
            repo.create_file('CODEOWNERS', commit_message, codeowners)
        # ensure that the configured team has access to the repo if it's a team
        if co_team:
            co_team.set_repo_permission(repo, 'admin')


    def _set_branch_protection(self, repo: Repository.Repository, has_codeowners: bool, reviewers=DEFAULT_REVIEWER_COUNT):
        # TODO: soft fail here
        main = repo.get_branch(repo.default_branch)
        main.edit_protection(required_approving_review_count=reviewers, require_code_owner_reviews=has_codeowners)
    
    def create_repo(self, name, template, visibility, team, description='') -> Tuple[str, Repository.Repository]:
        if self._check_repo_exists(name):
            raise RepoExistsError("github repo already exists")
        if template.lower() == 'none':
            cr = self._create_repo(name, visibility, description)
        else:
            cr = self._create_repo_from_template(name, template, visibility, description)
        if team is None or team.lower() == 'none':
            raise ValueError("team is required")
        self._add_codeowners(team, cr)
        self._set_branch_protection(cr, has_codeowners=True)
        return cr.html_url, cr

    def get_teams(self, include_users=True):
        # return early with cached list if we
        # have pulled in the last 10 min
        update = True
        if self._last_teams_pull:
            mins = (datetime.now() - self._last_teams_pull).seconds / 60
            if mins < 10:
                update = False
        if update:
            self._teams = []
            self._users = []
            for team in self._org.get_teams():
                self._teams.append(team)
            for user in self._org.get_members():
                self._users.append(user)
            # commenting out 'None' to enforce adding someone to CODEOWNERS
            # self._teams.append('None')
            self._last_teams_pull = datetime.now()
        # return a list of strings 
        teamstrings = []
        for team in self._teams:
            teamstrings.append(team.name)
        if include_users:
            for user in self._users:
                teamstrings.append(user.login)
        return teamstrings
        

if __name__ == "__main__":
    import os
    g = GitManager(os.getenv('GITHUB_TOKEN'), 'some_org')
    #t = g.get_teams()
    template = g.get_templates()
    # h, c = g.create_repo('TEST_REPO_jm_a', template, 'Private', 'security', '')
    # c.delete()
    # name, none, private, none
    # h, c = g.create_repo('TEST_REPO_jm_b', 'None', 'Private', 'None', '')
    #c.delete()
    # name, template, public, none
    #h, c = g.create_repo('TEST_REPO_jm_c', template, 'Public', 'None', '')
    #c.delete()
    # name, none, internal, security
    #h, c = g.create_repo('TEST_REPO_jm_d', 'None', 'Internal', 'security', '')
    #c.delete()