# SQLite Release 3.44.0 On 2023-11-01

Source ID: 0009
Source URL: https://www.sqlite.org/releaselog/3_44_0.html
Snapshot date: 2026-10-15 (Asia/Shanghai)
Raw SHA256: f9c130e89a072c9d27f4bdf740d2f0434acfda75f035d8f99aeeb6b1741574b5

---

## SQLite Release 3.44.0 On 2023-11-01

Aggregate functions can now include an ORDER BY clause after their last
parameter. The arguments to the function are processed in the order
specified. This can be important for functions like
string_agg() and json_group_array() .

Add support for the concat() and concat_ws() scalar SQL functions,
compatible with PostgreSQL, SQLServer, and MySQL.

Add support for the string_agg() aggregate SQL function, compatible
with PostgreSQL and SQLServer.

New conversion letters on the strftime() SQL function : %e %F %I %k %l %p %P %R %T %u

Add new C-language APIs: sqlite3_get_clientdata() and sqlite3_set_clientdata() .

Many errors associated with CREATE TABLE are now raised when the CREATE TABLE statement
itself is run, rather than being deferred until the first time the table is actually
used.

The PRAGMA integrity_check command now verifies the consistency of the
content in various built-in virtual tables using the new xIntegrity method .
This works for the FTS3 , FTS4 , FTS5 , RTREE , and GEOPOLY extensions.

The SQLITE_DBCONFIG_DEFENSIVE setting now prevents PRAGMA writable_schema
from being turned on. Previously writable_schema could be turned on, but would
not actually allow the schema to be writable. Now it simply cannot be turned on.

Tag the built-in FTS3 , FTS4 , FTS5 , RTREE , and GEOPOLY virtual tables as
SQLITE_VTAB_INNOCUOUS so that they can be used inside of triggers in
high-security deployments.

The PRAGMA case_sensitive_like statement is deprecated, as its use when the
schema contains LIKE operators can lead to reports of database corruption
by PRAGMA integrity_check .

SQLITE_USE_SEH (Structured Exception Handling) is now enabled by default whenever
SQLite is built using the Microsoft C compiler. It can be disabled using
-D SQLITE_OMIT_SEH .

Query planner optimizations:

In partial index scans, if the WHERE clause implies a constant value for a table
column, replace occurrences of that table column with the constant. This
increases the likelihood of the partial index being a covering index.

Disable the view-scan optimization (added in version 3.40.0 - item 3d)
as it was causing multiple performance regressions. In its place, reduce
the estimated row count for DISTINCT subqueries by a factor of 8.

SQLite now performs run-time detection of whether or not the underlying hardware
supports "long double" with precision greater than "double" and uses appropriate
floating-point routines depending on what it discovered.

The CLI for Windows now defaults to using UTF-8 for both input
and output on platforms that support it. The --no-utf8 option is available
to disable UTF8 support.

Hashes:

SQLITE_SOURCE_ID: 2023-11-01 11:23:50 17129ba1ff7f0daf37100ee82d507aef7827cf38de1866e2633096ae6ad8130

SHA3-256 for sqlite3.c: d9e6530096136067644b1cb2057b3b0fa51070df99ec61971f73c9ba6aa9a36e

A complete list of SQLite releases
in a single page and a chronology are both also available.
A detailed history of every
check-in is available at

SQLite version control site .
