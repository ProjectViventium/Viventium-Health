# Viventium-Health Privacy Policy

Effective date: July 27, 2026

Viventium-Health is a local-first, owner-operated health data bridge. It connects an owner's health
accounts to software that the same owner runs on their own computer. The open-source project does
not operate a hosted service, sell data, serve advertising, or create a central Viventium-Health
database.

## Data the app can access

When an owner explicitly authorizes the WHOOP connector, the app can request the WHOOP data scopes
selected on the WHOOP consent screen. These may include cycles, recovery, sleep, workouts, profile,
and body measurements. OAuth credentials and retrieved responses are health-sensitive private data.

## How data is used and stored

Viventium-Health uses authorized data only to create raw, timestamped, append-only evidence files
for the owner and to make bounded reads available to the owner's local AI tools. Requests travel
directly between the owner's local Viventium-Health process and the provider's official API.

Credentials and retrieved health data are stored on the owner's computer under the private local
Viventium application-support directory. They are not committed to the public source repository or
sent to a Viventium-Health-operated server. When an owner asks a connected AI to read a record, the
selected bounded chunk enters that AI system's context and may be retained in its ordinary
conversation/tool-result history under that system's privacy and retention policy. The owner
controls any separate AI provider or host system to which they choose to expose these local records.

## Sharing, sale, and advertising

The project does not sell health data, share it with advertisers, or use it for targeted advertising.
The open-source maintainers do not receive an owner's retrieved records through normal operation.

## Retention and deletion

Raw captures remain on the owner's computer until the owner deletes them. Disconnecting WHOOP
revokes the provider grant and removes the local OAuth token while retaining historical captures so
the owner does not lose evidence unexpectedly. An owner can delete the private Viventium-Health
storage directory to remove local credentials and captures.

## Security

Viventium-Health stores credentials and archives with owner-only filesystem permissions, writes
captures append-only, records hashes for integrity checks, and exposes health evidence to AI tools
through read-only bounded operations. No system can eliminate all risk, so owners should protect
their operating-system account and any AI providers they connect.

## Contact

For privacy or security questions, use the repository's private security-reporting channel when
available, or open a non-sensitive issue at
[ProjectViventium/Viventium-Health](https://github.com/ProjectViventium/Viventium-Health/issues).
Never include credentials or personal health data in a public issue.

## Changes

Material changes to this policy will be published in this repository with their effective date.
