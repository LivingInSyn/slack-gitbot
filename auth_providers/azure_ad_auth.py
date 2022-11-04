from adal import AuthenticationContext
import requests
import urllib.parse
import logging
import json
import os


class AzureADAuthManager:
    '''AzureADAuthManager allows for checking a particular users group membership.'''
    def __init__(self, conf: dict):
        # get the required values:
        # get the service account info
        cert_dir = conf['azure_ad_auth']['cert_dir']
        with open(os.path.join(cert_dir, 'key','key.pem'), 'r') as f:
            self._cert_text = f.read()
        with open(os.path.join(cert_dir, 'cert','cert.pem', 'r')) as f:
            self._key_text = f.read()
        self._session = requests.Session()
        self._thumbprint = conf['azure_ad_auth']['sa_key_thumprint']
        self._client_id = conf['azure_ad_auth']['client_id']
        self._auth_url = f'https://login.microsoftonline.com/{conf["azure_ad_auth"]["tennant_id"]}'
        self._group_id = conf['azure_ad_auth']['group_id']

    def _update_token(self):
        '''
        Updates the auth token for graphql. Microsoft caches the token for us, so calling
        it on every requyest is OK
        '''
        auth_context = AuthenticationContext(self._auth_url)
        # get a new token and update the session
        token_response = auth_context.acquire_token_with_client_certificate(
            resource='https://graph.microsoft.com', 
            client_id=self._client_id,
            certificate=self._key_text, 
            thumbprint=self._thumbprint, 
            public_certificate=self._cert_text
        )
        self._session.headers.update({'Authorization': "Bearer " + token_response['accessToken']})

    def _is_member_of(self, email: str):
        '''This function will check if a user passed in as an email is in the group_ip (a GUID) 
        passed'''
        self._update_token()
        email = urllib.parse.quote_plus(email)
        r = self._session.get(f'https://graph.microsoft.com/v1.0/users/{email}/transitiveMemberOf')
        if r.status_code != 200:
            # TODO: fix this with proper logging and stuff
            print("ERROR")
        groups = json.loads(r.text)
        for group in groups['value']:
            if group['id'] == self._group_id:
                return True
        return False

    def auth_request(self, logger, client, command, next, body, userid):
        user = client.users_profile_get(user=userid)
        email = user.data['profile']['email']
        if self._is_member_of(email, self._group_id):
            return True, ""
        else:
            return False, "You are not authorized to use the new git bot"