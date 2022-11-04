from adal import AuthenticationContext
import requests
import urllib.parse
import logging
import json


class AzureADAuthManager:
    '''AzureADAuthManager allows for checking a particular users group membership.'''
    def __init__(self, cert_text, key_text, thumbprint, client_id, tennant_id):
        self._session = requests.Session()
        self._cert_text = cert_text
        self._key_text = key_text
        self._thumbprint = thumbprint
        self._client_id = client_id
        self._auth_url = f'https://login.microsoftonline.com/{tennant_id}'

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

    def is_member_of(self, email: str, group_id: str):
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
            if group['id'] == group_id:
                return True
        return False