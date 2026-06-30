-- Local password accounts: hash stored here; NULL for Google/none users.
ALTER TABLE users ADD COLUMN password_hash TEXT;
