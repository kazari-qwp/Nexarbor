# SQLite Release 3.45.0 On 2024-01-15

Source ID: 0010
Source URL: https://www.sqlite.org/releaselog/3_45_0.html
Snapshot date: 2026-10-15 (Asia/Shanghai)
Raw SHA256: bcc8aaac97ea521887a3afb74b96fe1525ec0378efa71fc1289d3bd27285bfb7

---

## SQLite Release 3.45.0 On 2024-01-15

Added the SQLITE_RESULT_SUBTYPE property for
application-defined SQL functions .
All application defined SQL functions that invokes
sqlite3_result_subtype() must be registered with this new property.
Failure to do so might cause the call to sqlite3_result_subtype() to
behave as a no-op. Compile with -DSQLITE_STRICT_SUBTYPE=1 to cause an
SQL error to be raised if a function that is not SQLITE_RESULT_SUBTYPE
tries invokes sqlite3_result_subtype() . The use of -DSQLITE_STRICT_SUBTYPE=1
is a recommended compile-time option for every application that makes
use of subtypes.

Enhancements to the JSON SQL functions :

All JSON functions are rewritten to use a new internal parse tree
format called JSONB . The new parse-tree format is serializable
and hence can be stored in the database to avoid unnecessary re-parsing
whenever the JSON value is used.

New versions of JSON-generating functions generate binary JSONB instead
of JSON text.

The json_valid() function adds an optional second argument that
specifies what it means for the first argument to be "well-formed".

Add the FTS5 tokendata option to the FTS5 virtual table.

The SQLITE_DIRECT_OVERFLOW_READ optimization is now enabled by default.
Disable it at compile-time using -DSQLITE_DIRECT_OVERFLOW_READ=0.

Query planner improvements:

Do not allow the transitive constraint optimization to trick the
query planner into using a range constraint when a better equality
constraint is available.
( Forum post 2568d1f6e6 .)

The query planner now does a better job of disregarding
indexes that ANALYZE identifies as low-quality.
( Forum post 6f0958b03b .)

Increase the default value for SQLITE_MAX_PAGE_COUNT from 1073741824 to
4294967294.

Enhancements to the CLI :

Improvements to the display of UTF-8 content on Windows

Automatically detect playback of ".dump" scripts and make appropriate
changes to settings such as ".dbconfig defensive off" and
".dbconfig dqs_dll on".

Hashes:

SQLITE_SOURCE_ID: 2024-01-15 17:01:13 1066602b2b1976fe58b5150777cced894af17c803e068f5918390d6915b46e1d

SHA3-256 for sqlite3.c: f56d8e5e8c61d87b957f1cc60b3042c134d7bc0ca3aba002e6999e8f0af310a3

A complete list of SQLite releases
in a single page and a chronology are both also available.
A detailed history of every
check-in is available at

SQLite version control site .
