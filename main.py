from copy import deepcopy
from multiprocessing.sharedctypes import Value
import os
import json
import logging
from slack_bolt import App
from slack_sdk import WebClient
from auth_providers.auth_manager import AzureADAuthManager
from git_manager import GitManager, RepoExistsError

logging.basicConfig(level=logging.INFO-1)

app = App(
    token=os.environ.get("SLACK_BOT_TOKEN"),
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET"),
)

GIT_MANAGER: GitManager = None
MODAL_BLOCKS = None
# service account creds
SA_CERT_TEXT = ''
SA_KEY_TEXT = ''
SA_KEY_THUMBPRINT = ''
# group ID to check against in Azure AD
TENNANT_ID = ''
CLIENT_ID = ''
GROUP_ID = ''
# variable for the auth manager
AUTH_MANAGER = None


@app.middleware  # or app.use(log_request)
def log_request(logger, body, next):
    logger.info(body)
    return next()

@app.middleware
def auth_request(logger, client, command, next, body):
    userid = None
    if 'user' in body:
        userid = body['user']['id']
    elif 'user_id' in body:
        userid = body['user_id']
    if not userid:
        client.chat_postEphemeral(
            channel=user, 
            text=f'Sorry, something went wrong. UserID not found',
            user=user
        )
    user = client.users_profile_get(user=userid)
    email = user.data['profile']['email']
    if email.endswith('@puppet.com'):
        return next()
    elif AUTH_MANAGER.is_member_of(email, GROUP_ID):
        return next()
    else:
        client.chat_postEphemeral(
            channel=user, 
            text=f'You are not authorized to use the new git bot',
            user=user
        )

def _get_static_select_opt(text, value, emoji=True):
    return {
        "text": {
            "type": "plain_text",
            "text": text,
            "emoji": emoji
        },
        "value": value
    }

def get_modal_blocks():
    modal = deepcopy(MODAL_BLOCKS)
    for v in GIT_MANAGER.visibilities:
        opt = _get_static_select_opt(v, v.lower())
        modal['blocks'][3]['element']['options'].append(opt)
    # NOTE: this will require an update if there are more than 99 templates in the org
    for t in GIT_MANAGER.get_templates()[:99]:
        opt = _get_static_select_opt(t, t.lower())
        modal['blocks'][4]['element']['options'].append(opt)
    # for t in GIT_MANAGER.get_teams():
    #     opt = _get_static_select_opt(t, t.lower())
    #     modal['blocks'][5]['element']['options'].append(opt)
    return modal

def get_modal():
    blocks = get_modal_blocks()['blocks']
    view = {
        'type': 'modal',
        "callback_id": "submit-repo",
        'title': {
            'type': 'plain_text',
            'text': 'New Repository'
        },
        'submit': {
            'type': 'plain_text',
            'text': 'Create'
        },
        'blocks': blocks
    }
    return view

@app.command("/new-git")
def new_git(ack, client: WebClient, body, respond, command, logger):
    ack()
    # command['user_name']
    modal_view = get_modal()
    res = client.views_open(
        trigger_id = body["trigger_id"],
        view = modal_view
    )
    logger.info(res)

# https://github.com/slackapi/bolt-python/blob/main/examples/modals_app.py
@app.view("submit-repo")
def view_submission(ack, body, logger, client):
    ack()
    user = body["user"]["id"]
    client.chat_postEphemeral(
        channel=user,
        text="We're working on it 👍",
        user=user
    )
    #client.chat_postMessage(channel=user, message="We're working on it 👍")
    # TODO: log user
    state_vals = body["view"]["state"]["values"]
    repo_name = state_vals['name']['name_input']['value']
    vis = state_vals['vis']['vis_input']['selected_option']['value']
    template = state_vals['template']['template_input']['selected_option']['value']
    team = state_vals['team']['es_team_a']['selected_option']['value']
    try:
        new_url, _repo = GIT_MANAGER.create_repo(repo_name, template, vis, team)
    except RepoExistsError:
        client.chat_postEphemeral(
            channel=user, 
            text=f'Repo name already exists! Please try again.',
            user=user
        )
        return
    except Exception as e:
        logging.error(f"Error creating repo. Exception: {e}")
        client.chat_postEphemeral(
            channel=user, 
            text=f'Something went wrong! Please try again later',
            user=user
        )
        return
    client.chat_postEphemeral(
        channel=user, 
        text=f'New repo created: {new_url}',
        user=user
    )
    # logger.info(body["view"]["state"]["values"])

@app.options("es_team_a")
def show_teams(ack, payload):
    ack()
    options = {"options": []}
    try:
        steam = payload.get("value").lower()
    except:
        # TODO: log this
        ack(options)
    for team in GIT_MANAGER.get_teams():
        if team.lower().startswith(steam):
            o = {"text": {"type": "plain_text", "text": team}, "value": team}
            options['options'].append(o)
            if len(options['options']) >= 50:
                break
    ack (options)


def _get_env_var(var_name: str):
    e = os.getenv(var_name)
    if not e:
        raise ValueError(f"Missing {var_name}, exiting")
    return e

if __name__ == "__main__":
    # get the GitHub token and build git object
    gh_token = _get_env_var('GITHUB_TOKEN')
    org = _get_env_var('GITHUB_ORG')
    # get the service account info
    certdir = os.environ.get('SA_CERT_DIR', '/secrets')
    with open(f'{certdir}/cert/cert.pem', 'r') as f:
        SA_CERT_TEXT = f.read()
    with open(f'{certdir}/key/key.pem', 'r') as f:
        SA_KEY_TEXT = f.read()
    SA_KEY_THUMBPRINT = _get_env_var('SA_KEY_THUMBPRINT')
    CLIENT_ID = _get_env_var('CLIENT_ID')
    TENNANT_ID = _get_env_var('TENNANT_ID')
    # get the group ID for the group we're going to look for membership of
    GROUP_ID = _get_env_var('GROUP_ID')
    # setup the git manager
    GIT_MANAGER = GitManager(gh_token, org)
    # setup the auth manager. Only supports azure AD right now
    AUTH_MANAGER = AzureADAuthManager(SA_CERT_TEXT, SA_KEY_TEXT, SA_KEY_THUMBPRINT, 
        CLIENT_ID, TENNANT_ID)
    # fill in the modal blocks
    with open('blocks.json', 'r') as f:
        bj = f.read()
    MODAL_BLOCKS = json.loads(bj)
    app.start(port=int(os.environ.get("PORT", 3000)))
