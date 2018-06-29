# Clients
Client processes interact identically with the Redis and Legion Designs.

## GUI client

A Python/Qt process.
Scripted testing using Qt/Script.

[Here is a list](existing_clients.md) of existing clients from AMI-1.

## Web Browser Client
Using JavaScript visualization D3.js, [lexicon](lexicon.md).
Browser clients will connect to a web server using https and JSON.
The web server will support Epics and will talk to the backend.

## Device client

A client that does not display data visually but uses it for some other purpose.

## File client

A file client is mainly used for testing.
It reads and writes to files rather than a GUI.
