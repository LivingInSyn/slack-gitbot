# slack-gitbot
a slackbot using bolt 

## Environmental Variables
| Variable Name | Secret | Description |
| ------------- | ------ | ----------- |
| SLACK_BOT_TOKEN | True | The Slack bot token from the oauth tab of the bot configuration page in slack (`xoxb-<something>`) |
| SLACK_SIGNING_SECRET | True | The signing secret from the basic information page of the bot configuration page in slack |
| GITHUB_TOKEN | True | The github PAT used to create new repos |
| GITHUB_ORG| False | The name of the GitHub org to create repos in |
| SA_CERT_DIR | False | The directory prefix of where to search for `cert.pem` and `key.pem`. Not required, defaults to `/secrets` |
| SA_KEY_THUMBPRINT | False | The SHA1 thumbprint without `:` for the Azure AD service account certificate | 
| CLIENT_ID | False | The client ID for the app in AzureAD |
| TENNANT_ID | False | The tennant ID for the AzureAD Tennant |
| GROUP_ID | False | The group ID for the group to check membership of in AzureAD |


## Secrets
You must have configured the following secrets in your GCP Project before using/deploying this repo

* gitbot-signing-key (mapped to the `SLACK_SIGNING_SECRET` env var)
* gitbot-oauth-token (mapped to the `SLACK_BOT_TOKEN` env var)
* gitbot-github-token (mapped to the `GITHUB_TOKEN` env var)
* gitbot-azuread-cert (mapped to `/secrets/cert/cert.pem` in cloud run/docker)
* gitbot-azuread-key (mapped to `/secrets/key/key.pem` in cloud run/docker)

## Build and publish the container
This project is built with GCP cloud build and ran on GCP cloud run

## Configure slack
Use the `app_manifest.yml` to set the slack permissions

Dev:

`https://app.slack.com/app-settings/T0380EW89NC/A038D7VCURW/app-manifest`

Prod:

`https://app.slack.com/app-settings/TCJ3PFY94/A03E91UG1CH/app-manifest`


## Build cert for Azure AD
Make a certs directory and change to it

```shell
mkdir certs && cd certs
```

Create a key and a cert that expires in 1 year
```shell
openssl req -x509 -nodes -newkey rsa:4096 -keyout key.pem -out cert.pem -sha256 -days 365
```