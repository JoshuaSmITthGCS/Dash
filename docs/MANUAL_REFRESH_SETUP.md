# Configure manual refresh on Netlify

The portfolio and watchlist refresh buttons call a Netlify Function that verifies the signed-in
Firebase user and then starts the repository's `refresh-advisor.yml` GitHub Actions workflow. The
function needs four server-only environment variables before it can work.

## Before you start

You need:

- admin access to the Netlify project for `dash1212.netlify.app`
- admin access to the GitHub repository
- access to the Firebase project used by the website
- the email address you use to sign in to the website

Never commit any of the secret values below to Git, `.env` files, `netlify.toml`, screenshots, or
support messages.

## 1. Create the GitHub refresh token

1. Open GitHub **Settings → Developer settings → Personal access tokens → Fine-grained tokens**.
2. Select **Generate new token**.
3. Give it a clear name such as `Dash Netlify refresh`.
4. Choose an expiration date. Set a reminder to replace the token before it expires.
5. Set the resource owner to `JoshuaSmITthGCS`.
6. Under repository access, choose **Only select repositories** and select `Dash`.
7. Under **Repository permissions**, set **Actions** to **Read and write**.
8. Generate the token and copy it immediately.

The copied token is the value for `GITHUB_REFRESH_TOKEN`. Paste only the token itself—do not add
`Bearer`, quotation marks, or spaces.

GitHub documents the fine-grained token flow in
[Managing your personal access tokens](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens).
The workflow-dispatch API requires repository **Actions: write** permission, as shown in
[Create a workflow dispatch event](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event).

## 2. Download a Firebase service-account key

1. Open the [Firebase console](https://console.firebase.google.com/).
2. Select the project used by this website.
3. Open **Project settings → Service accounts**.
4. Select **Generate new private key**, confirm, and save the downloaded JSON file securely.
5. Open the JSON file in a text editor and copy its complete contents, from the first `{` through
   the final `}`.

The complete JSON object is the value for `FIREBASE_SERVICE_ACCOUNT_JSON`. Paste the JSON itself:

- do not paste the file path
- do not convert it to base64
- do not surround the whole object with another pair of quotation marks
- preserve the `\n` characters inside the `private_key` string

Firebase's official setup steps are in
[Add the Firebase Admin SDK to your server](https://firebase.google.com/docs/admin/setup).
Treat the downloaded key as a password. If it is exposed, delete that key in Firebase and generate
a replacement.

## 3. Add all four variables in Netlify

1. Open the `dash1212` project in Netlify.
2. Go to **Project configuration → Environment variables**.
3. Select **Add a variable** (or **Add environment variables**) and add the following:

| Variable | Value for this project |
| --- | --- |
| `GITHUB_REFRESH_TOKEN` | The fine-grained GitHub token created above |
| `REFRESH_GITHUB_REPOSITORY` | `JoshuaSmITthGCS/Dash` |
| `REFRESH_ALLOWED_EMAILS` | The Firebase sign-in email allowed to refresh |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | The complete Firebase service-account JSON |

For more than one authorized user, enter emails separated by commas:

```text
first@example.com,second@example.com
```

The email must be the same email shown by Firebase Authentication for that user. Capitalization
does not matter, but spelling does.

Configure the variables for the **Production** deploy context. If refresh should also work on
Netlify deploy previews, include **Deploy Previews** as well. If Netlify offers variable scopes,
select **Functions**. Netlify's documentation covers both
[creating environment variables](https://docs.netlify.com/build/environment-variables/get-started/)
and [using them in Functions](https://docs.netlify.com/build/functions/environment-variables/).

After saving the variables, open **Deploys** and trigger a new production deploy so the running
function definitely receives the new configuration.

## 4. Verify the server configuration

First run this unauthenticated check:

```bash
curl -i -X POST https://dash1212.netlify.app/.netlify/functions/refresh-data \
  -H 'Content-Type: application/json' \
  --data '{"symbols":["AAPL"]}'
```

The expected response after successful configuration is:

```text
HTTP/2 401
{"error":"Sign in before requesting a refresh."}
```

That `401` is intentional: it proves the function found its server configuration and then correctly
rejected a request without a Firebase sign-in token. A `503` with “Manual refresh is not
configured” means at least one of the first three variables is missing or empty.

Next:

1. Sign in to the website using an email listed in `REFRESH_ALLOWED_EMAILS`.
2. Add or confirm the portfolio/watchlist tickers you want updated.
3. Select the refresh button.
4. Confirm that the site reports that the refresh started.
5. Open GitHub **Dash → Actions → Refresh advisor data** and confirm a new run appears.
6. Let the workflow and subsequent Netlify deploy finish, then reload the page.

Button-triggered runs use the fast interactive scope: the prior top 100 stocks plus every portfolio
or watchlist ticker sent by the browser. The rest of the ranked universe carries forward from the
full 08:00 Eastern weekday sweep, so newly added symbols such as `MU`, `AMAT`, `NTNX`, or `VOO`
are refreshed without making the user wait for all ~900 stocks.

## Troubleshooting

| Result | Meaning | What to check |
| --- | --- | --- |
| `401` | No valid website sign-in token | Sign in to the website, then use its refresh button |
| `403` | Signed-in email is not authorized | Match `REFRESH_ALLOWED_EMAILS` to the Firebase user's email |
| `409` | A refresh workflow is already running | Wait for the current GitHub Actions run to finish |
| `503` | Configuration is missing or repository format is invalid | Check all variable names and use exactly `JoshuaSmITthGCS/Dash` |
| `500` | Firebase verification or GitHub API request failed | Check the service-account JSON, token expiration, repository access, and Actions permission |

If the token expires or either credential is rotated, replace its Netlify value and redeploy.
