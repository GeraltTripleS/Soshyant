# Document and group permissions

Restart the server and refresh the browser after updating. Sign in as an administrator. Existing documents remain shared unless you restrict them. The database adds the permission tables and watched-folder setting automatically; accounts, content and selected models are preserved.

## Give a team access

1. Open **Access groups**, choose **Create group**, give it a name and select its members. Save the group. Existing groups can be renamed or their membership changed with **Edit group**.
2. Open **Documents**, find a document and select **Access**.
3. Choose **Selected groups** and select the groups allowed to use this document. With no group selected, only administrators can access it. Choose **All signed-in users** to share it with everyone.

Administrators always have document access, including in the answer-quality review screen. Users can belong to several groups; membership in any granted group is sufficient. Inactive accounts cannot read documents, even if still listed as group members. Removing a group removes its grants and membership; affected documents remain restricted instead of becoming shared. Users may retain access through another group.

## Import confidential documents privately

Choose **Administrators only** under **Initial document access** before uploading a file or importing a document folder. That policy is recorded atomically before indexing starts. After indexing, grant the relevant groups through the document's **Access** button.

Watched folders have a **New file access** setting when created and on the existing folder card. This setting applies when a new file is approved; it does not modify the access rules of already published documents. Replacing a watched or manually uploaded document keeps the same document identity and existing access policy.

Initial access applies to the imported copy; it does not change any other copies already in the library. The shared option remains the default for compatibility. Choosing a private option before import avoids a period in which confidential content is shared while an administrator edits its permissions afterward.

## What the server enforces

Access is checked on the server when listing documents, retrieving passages, preparing model context, downloading current or historical file versions, returning conversation history, and returning completed answer jobs. Unauthorized passages are excluded before lexical/semantic ranking or model requests. Guessing a document ID does not bypass the download check.

New answers record every retrieved document and the document dependencies of earlier answers included in their context. If a user loses any required source, the entire saved answer and its citations are replaced with an access-change notice on later reads. Restricted historical content is also excluded from subsequent model context. Original stored content is retained for administrators and backups; this is access control, not history deletion.

Legacy answers created before dependency tracking are treated conservatively: if a user cannot access any restricted source in the installation, legacy answers without complete dependency records are hidden. Ask again to generate an answer from the currently permitted sources. Administrators can still read those historical records.

Changing a document policy, group membership or removing a group stops queued/running answer jobs. A final check before saving prevents an answer generated across an access change from being published. Users can retry with current access. Renaming a group without changing membership does not interrupt answers.

Already displayed, copied, exported, downloaded or transmitted content cannot be recalled. An API provider may already have received an authorized request when access is revoked. Open clients apply the new rules when they refresh or request history again; they are not remotely wiped. The server performs these checks for both desktop and Android clients, without requiring a new APK.

## Backups and retained policy records

Policies and groups are stored in the same local database and included in backups. Policy metadata is deliberately retained after deleting a document so its previously saved answer excerpts cannot become public through a missing permission record. No file content is retained by that policy metadata. Conversation deletion still removes its saved answers, feedback and review entries.

Restoring a backup restores its access policy too. Backups made before this feature contain the previous shared-library policy; review permissions before enabling team access after restoring an older backup. API model keys remain server-only and are not included in these database backups.
