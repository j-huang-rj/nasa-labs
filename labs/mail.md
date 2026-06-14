# HW1-2 - Mail
phkoan

## Outline
* Basic Configuration
* Authentication
* Email Sending
* Email Receiving
* Encryption
* Security
* Mailing List
* Email Filtering and Rewriting

## Basic Configuration (Preflight, 0%)
* The mail server should be responsible for the emails sent to `{STUID}.nasa` and `mail.{STUID}.nasa`.
  * `{STUID}` is same as the ID you use in HW1-1.
  * In the following pages, `<domain>` refers to both of these domains.
* MX records should point to `smtp.{STUID}.nasa`.
* `smtp.{STUID}.nasa` and `imap.{STUID}.nasa` should be configured (not empty).
  * They will be described in the following pages.

## Authentication (0%)
* No testcase for this.
* Add the following accounts to the email system (`username:password`).
  * `admin:admin`
  * `test:test`
* Allow the email system to authenticate via LDAP `[LDAP]`
  * The `[LDAP]` tag denotes that the testcase requires a LDAP server, the specifications for which will be released in HW1-3.
  * All users in `ta` groups under `dc={STUID},dc=nasa` in LDAP should be able to send and receive emails.

## Email Sending (6%) `[LDAP]`
* Preflight
  * No open relay.
  * If a user is not authenticated, it cannot send emails.
* You should provide the endpoint `smtp.{STUID}.nasa` in DNS for sending emails.
  * Both for local users (2%) and LDAP users `[LDAP]` in `ta` group (4%).
* Authenticated users are only permitted to send emails using `<username>@<domain>`.
* The domain `ta.nasa` should be resolved correctly and some testcases may send emails to `admin@ta.nasa`.

## Email Receiving (8%)
* You should provide the endpoint `imap.{STUID}.nasa` for viewing emails.
* All users should be able to view their emails through IMAP.
  * Local (3%) LDAP (4%) `[LDAP]`
* All emails matching the pattern `<username>+<any>@<domain>` should be delivered to `<username>@<domain>`. (1%)

## Encryption (4%)
* STARTTLS should be **enforced** for SMTP (on port 587). (2%)
  * Other testcases only test port 25.
* STARTTLS should be **enabled** for IMAP (on port 143). (2%)
* You should self-sign the certificates, and we will not verify them.

## Security (5%)
* SPF (1%)
  * Specify the IP address of your SMTP server in SPF record. (same as `smtp.{STUID}.nasa`)
  * Set SPF policy to soft fail.
* DKIM (3%)
  * Use `2026-na` as the selector.
  * All emails should be signed with your key.
* DMARC (1%)
  * Emails that fail DMARC should be "quarantined".
  * Set RUA report address to `dmarc-report-rua@${STUID}.nasa`.
* The records should be added for both managed domains.

## Mailing List (8%)
* You should provide a mailing list service.
* Mailing list is an email address that automatically forwards a single incoming message to multiple pre-defined recipient addresses (members).
* `local_users@<domain>` should be resolved to the users `admin` and `test`. (2%)
* You should provide an HTTP endpoint on `smtp.{STUID}.nasa:8000` for OJ to create and delete mailing lists. (6%) `[LDAP]`
  * `POST /list/create` with payload `{"name": <name>, "members": [<usernames>...]}`
    * Creates a mailing list named `<name>` with members `<usernames>`.
    * For example, `{"name": "ta", "members": ["phkoan", "ymlai"]}` creates a mailing list named "ta" with members "phkoan" and "ymlai".
  * `DELETE /list/<name>`
    * Deletes the mailing list named `<name>`.

## Email Filtering and Rewriting (10%)
* If an email subject contains `[SPAM]`, it should be rejected in the SMTP session at the gateway. (4%)
  * In other words, the email should NOT be queued by any SMTP servers.
* If an email body contains identification number, replace it with `***` (3 asterisks) to protect privacy. (4%)
  * The pattern of identification number is `[A-Z]\d{9}`.
* If an email is sent from the user `test`, the subject should be prefixed with `[TEST]`. (2%)

## Note
* It's guaranteed that using Postfix and Dovecot in Debian is sufficient to complete this assignment.
  * But you are encouraged to try alternative implementations, such as Stalwart.
* It's guaranteed that using exactly one machine is sufficient to complete this assignment.
  * But you are encouraged to design a system with more than one machines for this assignment, and we recommend to design the architecture prior to implementation.
* We ONLY grade on the behavior of your email servers, not your implementation.
