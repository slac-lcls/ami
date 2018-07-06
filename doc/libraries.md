# Common libraries

## ExceptionHandler
INFO, DEBUG, WARNING, ERROR, FATAL severities.
Exception propagates to user console, clients, log.

## Store
A wrapper around Redis with AMI features.
Save and restore state.
Define keys according to AMI semantics (e.g. access by node id, process, etc).
Startup after process crash.

