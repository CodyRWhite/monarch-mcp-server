# Monarch Money MCP Server

A Model Context Protocol (MCP) server for integrating with the Monarch Money personal finance platform. This server provides seamless access to your financial accounts, transactions, budgets, and analytics through Claude Desktop and Claude Code.

**Built with the [MonarchMoneyCommunity Python library](https://github.com/bradleyseanf/monarchmoneycommunity)** - an actively maintained community fork of the Monarch Money API with full MFA support.

## 🚀 Quick Start

If you plan to use this MCP server locally / on the same computer as Claude Desktop or similar, start with the [`Local Installation` section](#1-local-installation).

For other deployment scenarios - like containerized deployment or cloud hosting - start with the [`Containerized Deployment` section](#containerized-deployment).

### 1. Local Installation

1. **Clone this repository**:
   ```bash
   git clone https://github.com/CodyRWhite/monarch-mcp-server.git
   cd monarch-mcp-server
   ```

2. **Install dependencies**:

   **Using `uv`** (recommended — install it from [astral.sh/uv](https://docs.astral.sh/uv/getting-started/installation/) if you don't have it):
   ```bash
   uv sync --locked
   ```
   `--locked` installs exactly what `uv.lock` pins (hash-verified) and refuses to silently re-resolve against PyPI — without it, a launch could pick up a newer, unreviewed dependency version.

   **Using `pip`**:
   ```bash
   pip install -r requirements-lock.txt --require-hashes
   pip install -e . --no-deps
   ```
   `requirements-lock.txt` is generated from `uv.lock` and gives the pip path the same hash-pinned guarantee.

3. **Configure your MCP client.** Add this to Claude Desktop's config (**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`; **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`) or to `.mcp.json` in your project for Claude Code:

   ```json
   {
     "mcpServers": {
       "Monarch Money": {
         "command": "uv",
         "args": [
           "run",
           "--locked",
           "--project",
           "/path/to/your/monarch-mcp-server",
           "monarch-mcp-server"
         ]
       }
     }
   }
   ```

   Replace `/path/to/your/monarch-mcp-server` with your actual path. If your client's subprocess launcher doesn't inherit your shell's `$PATH` (common for GUI apps), replace `"command": "uv"` with the absolute path from `which uv`.

   Using `pip` instead of `uv`? Use `"command": "python"` and `"args": ["/path/to/your/monarch-mcp-server/src/monarch_mcp_server/server.py"]`.

4. **Restart your MCP client.**

### 2. One-Time Authentication Setup

**Important**: For security and MFA support, authentication is done outside of Claude.

Open a terminal and run:

```bash
cd /path/to/your/monarch-mcp-server
uv run python login_setup.py        # or: python login_setup.py
```

The script offers four login paths:

#### Option 0 (recommended): Sign-in window

Opens a small native browser window (WebView2 on Windows, WebKit on macOS, WebKitGTK on Linux) pointed at Monarch's login page. Log in normally — SSO and MFA both just work, since it's a real browser engine rendering Monarch's own page — and the session cookies are captured automatically once you're signed in. No DevTools, no copy-pasting.

Requires the optional `browser-login` extra:

```bash
uv sync --locked --extra browser-login
# or: pip install pywebview
```

If it isn't installed (or, on Linux, if no GTK+WebKit2GTK/Qt+QtWebEngine toolkit is found underneath it), the script tells you what's missing, offers to install it for you — a plain `pip install pywebview` runs after a yes; a Linux system package install runs as its own separate confirmation, since that one needs `sudo` — and falls back to the option 1 menu below with instructions for installing it manually later.

#### Option 1 (recommended fallback): Session cookies from your browser

Long-lived, supports SSO accounts, and sidesteps Cloudflare CAPTCHA gates on programmatic login.

1. Log in to https://app.monarch.com in Chrome or Firefox.
2. Open DevTools (F12) → Network tab, click any request whose Name starts with `graphql` (or any request to `api.monarch.com`).
3. Scroll to Request Headers, find the `cookie:` header, and copy the full value.
4. Save it to the cookie file for your platform, then re-run the script — it reads the file automatically (pasting at the prompt instead can silently truncate on macOS/Linux terminals, so the file is the reliable path):

   - **macOS / Linux**: `~/.config/monarch-mcp/cookie.txt` (respects `$XDG_CONFIG_HOME`) — `mkdir -p ~/.config/monarch-mcp && chmod 600 ~/.config/monarch-mcp/cookie.txt` after pasting the value in.
   - **Windows**: `%APPDATA%\monarch-mcp\cookie.txt` — your user-profile ACLs already restrict it, no `chmod` equivalent needed.
   - Override the location on any platform with the `MONARCH_MCP_COOKIE_FILE` environment variable.

The script verifies the cookies against the live API before saving them to your system keyring. The cookie file is only read at setup time; the running MCP server uses the keyring session.

#### Option 2: Email and password

Standard interactive login. The script handles:

- Email verification codes (Monarch may send one for a new device session even when MFA is off).
- TOTP MFA codes if you have MFA enabled.
- Cloudflare CAPTCHA detection: if Monarch blocks programmatic login, the script tells you to switch to option 1.

The resulting long-lived session token is saved to your system keyring.

#### Option 3: Legacy session token paste

Kept for users with an existing token captured before the May 2026 API change. Monarch may no longer accept token-only auth on the GraphQL endpoint; if the verification call returns 401, fall back to option 1.

### 3. Start Using

Once authenticated, use these tools directly in Claude Desktop or Claude Code:

- `get_accounts` - View all your financial accounts
- `get_transactions` - Recent transactions with filtering
- `get_budgets` - Budget information and spending
- `get_cashflow` - Income/expense analysis

## Containerized Deployment

The Docker image uses Astral's uv/Python 3.12 slim base, installs from `uv.lock`,
and defaults to HTTP on `0.0.0.0:8000` inside the container.

### Build the image

```bash
docker build -t monarch-mcp-server .
```

### Authenticate

Authenticate once using a persistent session volume:

```bash
docker run --rm -it \
  -v monarch-session:/home/app/.monarch-mcp-server \
  monarch-mcp-server python login_setup.py
```

For cookie-based login (option 1), mount your cookie file at `/tmp/monarch-cookie.txt:ro` and set `MONARCH_MCP_COOKIE_FILE=/tmp/monarch-cookie.txt` on the login container. The container's uid `10001` needs read access to it — either `chown 10001 cookie.txt` (keep it at mode 0600, don't widen it) or run the login container with `--user $(id -u)`. Delete the file once login succeeds.

Once saved, the session volume is sufficient for normal server launches.

> [!IMPORTANT]
> **The session is stored unencrypted in that volume.** This differs from a
> local install, and the difference is easy to miss.
>
> On macOS and Windows the session goes to the system keyring. A container has
> no keyring backend, so storage falls back to a file. That file is encrypted
> at rest only on Windows, through DPAPI, so in a Linux container it holds your
> Monarch session in plaintext. Permissions are as tight as a file can be, mode
> 0600 inside a 0700 directory owned by uid 10001, but file permissions do not
> help against anyone who can reach the volume from outside the container.
>
> Treat `monarch-session` as a secret. It can be read by root on the Docker
> host, by any user in the `docker` group, by any other container that mounts
> the same volume, by `docker cp` and `docker exec`, and by anything that backs
> up `/var/lib/docker`. A Monarch session grants full read and write access to
> your accounts and does not expire on its own, so a copy of this volume is a
> lasting credential. Back it up only to somewhere you would keep a password,
> and delete the volume with `docker volume rm monarch-session` when you are
> done with it.
>
> The cookie file described below is the same kind of secret. Delete it once
> the login has succeeded; it is only needed for that one run.

### Start the HTTP server

Reuse the session volume when starting the server:

```bash
$ docker run -d --name monarch-mcp --restart unless-stopped \
  -p 127.0.0.1:8000:8000 \
  -v monarch-session:/home/app/.monarch-mcp-server \
  monarch-mcp-server
```

Connect your MCP client to `http://127.0.0.1:8000/mcp` using Streamable HTTP.
See [HTTP transport configuration](#http-transport-configuration) for all settings.

### Connect from another machine

> [!WARNING]
> This MCP server is not multi-user or multi-account. All connected clients share the same session and permissions.
> Ensure that you understand the security implications before exposing the server to a network.

To connect from another machine, **put the container behind an authenticated HTTPS reverse proxy or a private network with access controls**, publish the port on the appropriate interface, and allow the hostname used by the client:

```bash
docker run -d --name monarch-mcp --restart unless-stopped \
  -p 127.0.0.1:8000:8000 \
  -e MONARCH_MCP_ALLOWED_HOSTS=mcp.example.com \
  -v monarch-session:/home/app/.monarch-mcp-server \
  monarch-mcp-server
```

A reverse proxy on the Docker host forwards `https://mcp.example.com/mcp` to `http://127.0.0.1:8000/mcp`, preserving the public Host header, and must support streaming responses without buffering. For direct access on a private network instead, allow the client's Host value including the port (e.g. `server.lan:8000`).

Host/origin checks protect against DNS rebinding; they do not authenticate callers, and all connected clients share the same saved Monarch session and write-tool access. Use one server and session volume per Monarch account if you need to.

### Use STDIO instead

To run the Docker image over STDIO instead:

```bash
docker run --rm -i \
  -e MONARCH_MCP_TRANSPORT=stdio \
  -v monarch-session:/home/app/.monarch-mcp-server \
  monarch-mcp-server
```

## HTTP Transport Configuration

The server supports MCP Streamable HTTP at `/mcp` but only when explicitly selected:

```bash
uv run --locked monarch-mcp-server --transport http --host 127.0.0.1 --port 8000
```

Connect an MCP client using Streamable HTTP to `http://127.0.0.1:8000/mcp`.

| Setting                            | CLI flag                        | Environment variable                            | Default outside Docker                         |
| ---------------------------------- | ------------------------------- | ----------------------------------------------- | ---------------------------------------------- |
| Transport                          | `--transport`                   | `MONARCH_MCP_TRANSPORT`                         | `stdio` (`http` aliases `streamable-http`)     |
| Listen address                     | `--host`                        | `MONARCH_MCP_HOST`                              | `127.0.0.1`                                    |
| Listen port                        | `--port`                        | `MONARCH_MCP_PORT`                              | `8000`                                         |
| Additional allowed Host headers    | `--allowed-host` (repeatable)   | `MONARCH_MCP_ALLOWED_HOSTS` (comma-separated)   | None; loopback hosts are always allowed        |
| Additional allowed browser Origins | `--allowed-origin` (repeatable) | `MONARCH_MCP_ALLOWED_ORIGINS` (comma-separated) | None; HTTP loopback origins are always allowed |

CLI flags override their environment settings.
Host entries include the port when clients send one; `server.lan:*` allows any port.
Origin entries include the scheme, for example `https://client.example.com`.
Clients without an Origin header are supported.
Browser clients may additionally require CORS handling at the reverse proxy.

## ✨ Features

Full read/write access to accounts, transactions, categories, tags, auto-categorization rules, merchants, recurring streams, splits, budgets, goals, and net worth — see [Available Tools](#️-available-tools) below for the complete list with parameters.

Authentication is one-time: sign in via the [sign-in window](#option-0-recommended-sign-in-window) (SSO and MFA both just work) or the cookie/password/token fallbacks, and the session persists in your system keyring across restarts — credentials never pass through Claude itself.

## 🛠️ Available Tools

All 58 registered tools. Required parameters are listed first, optional ones
are marked with a trailing question mark. This table is generated from the
live tool registry and the functions' signatures, so it does not drift.

| Tool                              | Description                                                                   | Parameters                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| --------------------------------- | ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `add_transaction_tag`             | Add a tag to a transaction, preserving any tags already on it                 | `transaction_id`, `tag_id`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| `bulk_categorize_transactions`    | Apply the same category to multiple transactions at once                      | `transaction_ids`, `category_id`, `mark_reviewed`?, `dry_run`?                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| `categorize_transaction`          | Assign a category to a transaction                                            | `transaction_id`, `category_id`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| `check_auth_status`               | Report the stored session and its auth mode                                   | None                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `create_transaction`              | Create a new transaction in Monarch Money                                     | `date`, `account_id`, `amount`, `merchant_name`, `category_id`, `notes`?, `update_balance`?                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| `create_transaction_category`     | Create a new transaction category                                             | `group_id`, `transaction_category_name`, `icon`?, `rollover_enabled`?, `rollover_type`?                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| `create_transaction_rule`         | Create a new transaction auto-categorization rule                             | `merchant_criteria_operator`?, `merchant_criteria_value`?, `merchant_criteria_values`?, `merchant_criteria`?, `original_statement_operator`?, `original_statement_values`?, `original_statement_criteria`?, `use_original_statement`?, `amount_operator`?, `amount_value`?, `amount_lower`?, `amount_upper`?, `amount_is_expense`?, `set_category_id`?, `set_merchant_name`?, `add_tag_ids`?, `link_goal_id`?, `hide_from_reports`?, `review_status`?, `account_ids`?, `category_ids`?, `apply_to_existing`?                                                                                                             |
| `create_transaction_tag`          | Create a new transaction tag                                                  | `name`, `color`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| `debug_session_loading`           | Diagnose session loading problems                                             | None                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `delete_transaction`              | Delete a transaction from Monarch Money                                       | `transaction_id`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| `delete_transaction_rule`         | Delete a transaction rule                                                     | `rule_id`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| `get_account_balance_history`     | Get historical balance data for a specific account                            | `account_id`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| `get_account_holdings`            | Get investment holdings for a specific account                                | `account_id`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| `get_account_sync_health`         | Report the health of each linked institution connection                       | `stale_after_days`?                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| `get_accounts`                    | Get all financial accounts from Monarch Money                                 | None                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `get_budgets`                     | Get budget information from Monarch Money                                     | `start_date`?, `end_date`?                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| `get_cashflow`                    | Get cashflow analysis from Monarch Money                                      | `start_date`?, `end_date`?                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| `get_cashflow_by_month`           | Get spending trends over time, broken down by category and month              | `start_date`, `end_date`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| `get_category_details`            | Get a single category's details including budget amounts for a month          | `category_id`, `month`?                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| `get_debt_paydown`                | Get the debt paydown plan and the accounts feeding it                         | `method`?                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| `get_goal_contributions`          | Show a goal's budgeted contributions, broken down by funding account          | `goal_id`, `month`?                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| `get_goals`                       | List Monarch savings and debt-paydown goals                                   | None                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `get_merchant`                    | Get a merchant's details including recurring transaction stream configuration | `merchant_id`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| `get_net_worth`                   | Get net worth history over time                                               | `start_date`?, `end_date`?, `account_type`?                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| `get_net_worth_by_account_type`   | Get net worth breakdown by account type over time                             | `start_date`, `timeframe`?                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| `get_recurring_transactions`      | Get upcoming recurring transactions                                           | `start_date`?, `end_date`?                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| `get_spending_summary`            | Get a spending summary broken down by category, category group, and merchant  | `start_date`?, `end_date`?                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| `get_transaction_categories`      | Get all available transaction categories from Monarch Money                   | None                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `get_transaction_category_groups` | Get all transaction category groups (parent groupings for categories)         | None                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `get_transaction_details`         | Get full details for a specific transaction                                   | `transaction_id`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| `get_transaction_rules`           | Get all transaction auto-categorization rules from Monarch Money              | None                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `get_transaction_splits`          | Get the splits for a transaction                                              | `transaction_id`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| `get_transaction_tags`            | Get all available transaction tags from Monarch Money                         | None                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `get_transactions`                | Get transactions from Monarch Money                                           | `limit`?, `offset`?, `start_date`?, `end_date`?, `account_id`?, `search`?, `category_ids`?, `category_group_ids`?, `account_ids`?, `tag_ids`?, `has_notes`?, `is_split`?, `is_recurring`?, `wide_search`?, `search_scan_limit`?                                                                                                                                                                                                                                                                                                                                                                                          |
| `get_transactions_needing_review` | Get transactions that need review based on various criteria                   | `needs_review`?, `days`?, `uncategorized_only`?, `without_notes_only`?, `limit`?, `offset`?, `account_id`?                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| `get_transactions_summary`        | Get a high-level summary of transactions                                      | None                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `mark_transaction_reviewed`       | Mark a transaction as reviewed (clears the needs_review flag)                 | `transaction_id`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| `monarch_login`                   | Sign in via a secure form in the client UI                                    | None                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `monarch_login_with_token`        | Sign in with a browser copied session token                                   | None                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `monarch_logout`                  | Clear the stored session and drop the cached client                           | None                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `monarch_whoami`                  | Report who is signed in and what the account's plan entitles it to            | None                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `refresh_accounts`                | Request account data refresh from financial institutions                      | `account_ids`?                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| `reorder_transaction_rule`        | Move a transaction rule to a new position in the evaluation order             | `rule_id`, `new_order`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| `review_recurring_stream`         | Set the review status of a recurring transaction stream                       | `stream_id`, `review_status`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| `search_transactions`             | Search and filter transactions with comprehensive filtering options           | `search`?, `limit`?, `offset`?, `start_date`?, `end_date`?, `category_ids`?, `account_ids`?, `tag_ids`?, `has_attachments`?, `has_notes`?, `hidden_from_reports`?, `is_split`?, `is_recurring`?                                                                                                                                                                                                                                                                                                                                                                                                                          |
| `set_budget_amount`               | Set or update a budget amount for a category or category group                | `amount`, `category_id`?, `category_group_id`?, `start_date`?, `apply_to_future`?                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| `set_goal_contribution`           | Set the budgeted monthly contribution to a goal from one funding account      | `goal_id`, `account_id`, `amount`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| `set_transaction_tags`            | Set tags on a transaction                                                     | `transaction_id`, `tag_ids`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| `setup_authentication`            | Get setup instructions                                                        | None                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `split_transaction`               | Split a transaction into multiple parts with different categories/merchants   | `transaction_id`, `splits`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| `update_account`                  | Update an account's name, balance, type or visibility settings                | `account_id`, `name`?, `balance`?, `account_type`?, `account_sub_type`?, `include_in_net_worth`?, `hide_from_summary_list`?, `hide_transactions_from_reports`?, `dry_run`?                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| `update_category`                 | Update an existing category's settings                                        | `category_id`, `name`?, `icon`?, `group_id`?, `category_type`?, `exclude_from_budget`?, `budget_variability`?, `rollover_enabled`?, `rollover_start_month`?, `rollover_starting_balance`?, `rollover_frequency`?, `rollover_target_amount`?, `rollover_type`?, `confirm_rollover_reset`?, `dry_run`?                                                                                                                                                                                                                                                                                                                     |
| `update_merchant`                 | Update a merchant's name and/or recurring transaction stream settings         | `merchant_id`, `name`?, `is_recurring`?, `frequency`?, `base_date`?, `amount`?, `is_active`?                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| `update_savings_goal`             | Update a savings goal's target or monthly contribution                        | `goal_id`, `target_amount`?, `target_date`?, `name`?, `priority`?, `goal_type`?, `is_sinking_fund`?                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| `update_transaction`              | Update an existing transaction in Monarch Money                               | `transaction_id`, `category_id`?, `merchant_name`?, `goal_id`?, `amount`?, `date`?, `hide_from_reports`?, `needs_review`?, `notes`?                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| `update_transaction_notes`        | Update the notes/memo for a transaction                                       | `transaction_id`, `notes`, `receipt_url`?                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| `update_transaction_rule`         | Update an existing transaction rule                                           | `rule_id`, `merchant_criteria_operator`?, `merchant_criteria_value`?, `merchant_criteria_values`?, `merchant_criteria`?, `original_statement_operator`?, `original_statement_values`?, `original_statement_criteria`?, `use_original_statement`?, `amount_operator`?, `amount_value`?, `amount_lower`?, `amount_upper`?, `amount_is_expense`?, `set_category_id`?, `set_merchant_name`?, `add_tag_ids`?, `link_goal_id`?, `hide_from_reports`?, `review_status`?, `account_ids`?, `category_ids`?, `clear_category`?, `clear_merchant`?, `clear_tags`?, `clear_goal_link`?, `clear_review_status`?, `apply_to_existing`? |
| `upload_account_balance_history`  | Upload corrected balance snapshots for an account                             | `account_id`, `corrections`, `dry_run`?                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |

## 📝 Usage Examples

Just describe what you want in plain language — the model picks the tool. A few examples across the range of what's available:

```
Show me all my financial accounts
Show me my last 50 transactions and flag anything that needs review
Set my grocery budget to $600 for this month and apply it to all future months
Show my net worth trend for the past year, broken down by account type
Find all Amazon transactions from last month and categorize them as Shopping
Create a rule to auto-categorize Netflix as Shopping, then split this $100 Costco charge into $60 Groceries / $40 Household
```

`get_transactions`/`search_transactions` return a self-describing envelope (`tool`, `args`, `count`, `total_count`, `truncated`, `search`, `data`) rather than a bare list, so a truncated result is visible rather than silently mistaken for the full set. When Monarch's server-side search errors or returns nothing, `wide_search` scans recent transactions locally across merchant, statement text, notes, category, account, and tags instead.

See [Available Tools](#️-available-tools) above for every tool's exact parameters.

## 📅 Date Formats

- All dates should be in `YYYY-MM-DD` format (e.g., "2024-01-15")
- Transaction amounts: **positive** for income, **negative** for expenses

## 🔧 Troubleshooting

### Authentication Issues
If you see "Authentication needed" errors:
1. Run the setup command: `cd /path/to/your/monarch-mcp-server && python login_setup.py` (or `uv run python login_setup.py`)
2. Restart Claude Desktop or Claude Code
3. Try using a tool like `get_accounts`

### Email Verification Required
Monarch may require an email one-time code for a new device or session, even if MFA is not enabled. If you see an email-code prompt:
1. Check the email address on your Monarch account
2. Enter the one-time code in `login_setup.py`
3. Let the script finish so it can save the reusable token to your system keyring

### Session Expired or 401 within an hour
If your session dies quickly (under a couple of hours), the most common cause is that Monarch returned a short-lived token. The login script now requests `trusted_device=True` and rejects any short-lived token, so a fresh login produces a long-lived session. If you re-run `login_setup.py` and the issue persists, switch to option 0 (sign-in window) or option 1 (browser cookies); both track the lifetime of the underlying browser login rather than a token Monarch can expire early.

### Cloudflare CAPTCHA on login
If `login_setup.py` reports "Programmatic login is blocked by Cloudflare CAPTCHA", choose option 0 (sign-in window) or option 1 (browser cookies) instead. Email/password POSTs to Monarch's login endpoint are sometimes gated by Cloudflare for unfamiliar IPs or rapid retries; both cookie-based paths bypass that endpoint entirely by using a real browser to sign in instead.

### `'Context' object has no attribute 'elicit'`
The `monarch_login` and `monarch_login_with_token` tools require the MCP Python SDK 1.10.0 or newer (released June 2025). If your environment cached an older `mcp` install, refresh it:

```bash
uv cache clean mcp
```

Then fully quit and reopen Claude Desktop or Claude Code so it relaunches the server with a fresh resolution. As a fallback while you upgrade, run `python login_setup.py` from the repo to authenticate via the terminal.

### Common Error Messages
- **"No valid session found"**: Run `python login_setup.py` (or `uv run python login_setup.py`) 
- **"Monarch sent a one-time code to your email"**: Run `python login_setup.py` and complete email verification
- **"Invalid account ID"**: Use `get_accounts` to see valid account IDs
- **"Date format error"**: Use YYYY-MM-DD format for dates

## 🏗️ Technical Details

### Project Structure
```
monarch-mcp-server/
├── src/monarch_mcp_server/
│   ├── __init__.py
│   ├── app.py             # FastMCP app instance and entry point
│   ├── auth.py             # Elicitation-based login tools (monarch_login, monarch_logout)
│   ├── browser_login.py   # Embedded-browser sign-in window (optional, login_setup.py only)
│   ├── client.py          # Cached MonarchMoney client factory
│   ├── helpers.py          # Shared tool helpers (error/response formatting, date normalization)
│   ├── monarch_auth.py    # Current Monarch auth compatibility (host, email OTP, device-uuid)
│   ├── read_only.py        # MONARCH_MCP_READ_ONLY gate: unregisters mutating tools
│   ├── secure_session.py  # Keyring-backed token storage (file fallback)
│   ├── server.py          # Backward-compatibility shim re-exporting the tools
│   └── tools/             # MCP tools grouped by domain (accounts, transactions, budgets, …)
├── login_setup.py         # Terminal authentication script
├── pyproject.toml         # Project configuration
├── requirements-lock.txt  # Generated from uv.lock, hash pinned
└── README.md             # This documentation
```

### Session Management
- Session tokens are stored securely in the system keyring (with an automatic file fallback for environments without a keyring backend)
- On macOS, that fallback is disabled: Keychain access is expected to always work there, so a save or load that can't reach it fails loudly instead of writing an unencrypted file. A plaintext file left over from an older install is migrated into Keychain and deleted the next time it's loaded successfully.
- The `device-uuid` captured at login is stored alongside the token so it reloads cleanly
- Sessions persist across Claude Desktop and Claude Code restarts
- No need for frequent re-authentication

### Security Features
- Credentials never transmitted through Claude Desktop or Claude Code
- MFA/2FA fully supported
- Email verification codes are handled only in the terminal setup script
- Session tokens are stored in the system keyring — on macOS, only the keyring; the plaintext file fallback used on other platforms is refused
- Authentication handled in secure terminal environment

### Strongest option: read only mode

Set `MONARCH_MCP_READ_ONLY=1` in the server's environment and the mutating
tools are never registered. They do not appear in the tool list and cannot be
called at all, which is stronger than an approval prompt: a model that was
talked into a write by a merchant name or memo it read back cannot invoke a
tool that is not there.

```json
{
  "mcpServers": {
    "Monarch Money": {
      "command": "uv",
      "args": ["run", "--project", "/path/to/your/monarch-mcp-server", "monarch-mcp-server"],
      "env": { "MONARCH_MCP_READ_ONLY": "1" }
    }
  }
}
```

This leaves 30 of the 58 tools available, covering everything that reads.
Read only is off by default, so existing setups are unaffected. Note that it
also removes the login and logout tools, since those change durable state, so
authenticate with `login_setup.py` before enabling it.

### Recommended: require approval for mutating tools

These tools mutate your Monarch data. The list is every registered tool that writes, checked against the source rather than maintained by hand:

**Accounts**: `update_account`

**Transactions**: `create_transaction`, `update_transaction`, `delete_transaction`, `categorize_transaction`, `update_transaction_notes`, `mark_transaction_reviewed`, `bulk_categorize_transactions`, `split_transaction`, `upload_account_balance_history`

**Tags**: `set_transaction_tags`, `add_transaction_tag`, `create_transaction_tag`

**Rules**: `create_transaction_rule`, `update_transaction_rule`, `delete_transaction_rule`, `reorder_transaction_rule`

**Categories and budgets**: `create_transaction_category`, `update_category`, `set_budget_amount`

**Goals**: `update_savings_goal`, `set_goal_contribution`

**Merchants**: `update_merchant`, `review_recurring_stream`

**Session**: `monarch_login`, `monarch_login_with_token`, `monarch_logout`

`refresh_accounts` is side effecting too, since it posts a refresh request to your institutions, though it does not change your ledger.

Because the LLM can be influenced by data it reads back (a malicious-looking memo or merchant name in a transaction), the safest setup is to configure your MCP client to require manual approval before any mutating tool runs. In Claude Desktop and Claude Code this is the default behavior for unknown tools; keep it that way for the tools listed above rather than allow-listing them.

`bulk_categorize_transactions`, `upload_account_balance_history`, `update_account` and `update_category` accept a `dry_run=True` argument that returns the planned changes without executing them, useful for previewing before approving.

`update_category` additionally requires `confirm_rollover_reset=True` before `rollover_start_month` or `rollover_starting_balance` will be applied. Those two restart a category's rollover period and discard the balance accumulated in it, which cannot be undone, so they cannot ride along unnoticed in a call that otherwise reads like a rename.

## 🙏 Acknowledgments

This MCP server is built on top of the [MonarchMoneyCommunity Python library](https://github.com/bradleyseanf/monarchmoneycommunity), an actively maintained community fork of the original [MonarchMoney library](https://github.com/hammem/monarchmoney) by [@hammem](https://github.com/hammem). The community fork provides:

- Updated API endpoints for Monarch Money's current domain
- Secure authentication with MFA support
- Comprehensive API coverage for Monarch Money
- Session management and persistence

Thank you to [@hammem](https://github.com/hammem) for creating and maintaining this essential library!

## 📄 License

MIT License

## 🆘 Support

For issues:
1. Check authentication with `check_auth_status`
2. Run the setup command again: `cd /path/to/your/monarch-mcp-server && python login_setup.py`
3. Check error logs for detailed messages
4. Ensure Monarch Money service is accessible

## 🔄 Updates

To update the server:
1. Pull latest changes from repository
2. Restart Claude Desktop or Claude Code
3. Re-run authentication if needed: `python login_setup.py`
