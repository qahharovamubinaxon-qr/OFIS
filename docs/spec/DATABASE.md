# DATABASE DESIGN

Version 1.0

Database Engine

SQLite

Future

PostgreSQL

MySQL

SQL Server

Database layer must be abstracted through Repository Pattern.

Never access SQLite directly from UI.

---

# TABLES

The application database consists of the following tables.

companies

employees

employee_documents

passport_data

patent_data

registration_data

migration_cards

generated_documents

history

logs

settings

api_providers

user_preferences

archive

backups

document_templates

ocr_results

notifications

updates

search_index

system_info

statistics

licenses

sessions

errors

future_jobs

---

# TABLE

companies

Columns

id

uuid

name

internal_code

logo_path

template_path

description

status

notes

created_at

updated_at

archived_at

Indexes

name

internal_code

status

---

# TABLE

employees

Columns

id

uuid

company_id

surname

name

patronymic

gender

birth_date

nationality

created_at

updated_at

Foreign Key

company_id

Indexes

surname

passport

company

---

# TABLE

passport_data

Columns

id

employee_id

series

number

issue_date

issued_by

birth_place

gender

nationality

scan_path

ocr_json

confidence

created_at

---

# TABLE

patent_data

Columns

id

employee_id

series

number

profession

issue_date

expiration_date

region

scan_path

ocr_json

confidence

created_at

---

# TABLE

registration_data

Columns

id

employee_id

address

registration_date

expiration_date

scan_path

ocr_json

confidence

created_at

---

# TABLE

migration_cards

Columns

id

employee_id

number

entry_date

purpose

scan_path

ocr_json

confidence

created_at

---

# TABLE

document_templates

Columns

id

company_id

template_name

template_path

version

is_default

created_at

---

# TABLE

generated_documents

Columns

id

employee_id

company_id

template_id

pdf_path

generation_time

file_size

status

created_at

---

# TABLE

ocr_results

Columns

id

employee_id

provider

raw_json

normalized_json

confidence

processing_time

created_at

---

# TABLE

history

Columns

id

employee_id

company_id

action

description

created_at

---

# TABLE

logs

Columns

id

level

module

message

stack_trace

created_at

---

# TABLE

settings

Columns

id

language

theme

ai_provider

output_folder

archive_folder

auto_backup

logging_enabled

created_at

---

# TABLE

api_providers

Columns

id

provider

api_key

base_url

enabled

priority

created_at

---

# TABLE

archive

Columns

id

employee_id

company_id

folder

file_name

created_at

---

# TABLE

notifications

Columns

id

employee_id

type

message

read

created_at

---

# TABLE

statistics

Columns

id

total_documents

total_employees

total_companies

ocr_time

pdf_time

last_generated

---

# RELATIONSHIPS

Company

↓

Employees

↓

Passport

↓

Patent

↓

Registration

↓

Migration Card

↓

Generated Documents

↓

History

---

# DATABASE RULES

Never delete employee history.

Never overwrite PDFs.

Never overwrite OCR results.

Always create history records.

Always keep previous versions.

---

# SEARCH INDEX

Indexed fields

Surname

Name

Passport Number

Patent Number

Company

Profession

Registration Address

Document Number

Generated Date

---

# BACKUP

Automatic backup

Every day

Compressed

backup/

YYYY/

MM/

database.db

---

# ARCHIVE STRUCTURE

archive/

2026/

07/

APELKANS/

ABDULLAEV_JASUR/

passport.jpg

patent.jpg

registration.jpg

migration.jpg

generated.pdf

ocr.json

log.txt

---

# DATA FLOW

Upload Images

↓

OCR

↓

Normalize

↓

Validation

↓

Save Database

↓

Generate PDF

↓

Archive

↓

History

↓

Statistics

---

# FUTURE DATABASE SUPPORT

PostgreSQL

MySQL

SQL Server

Cloud Database

Repository Layer must allow changing database without modifying business logic.

---

# PERFORMANCE

Indexes required on

surname

passport_number

patent_number

company_id

employee_id

created_at

All search operations should complete in less than 100 milliseconds on 100,000+ employee records.

---

# DATA INTEGRITY

Use UUIDs for all primary business entities.

Validate foreign keys.

Prevent duplicate passport entries when configured.

Maintain audit history for every update.

Never permanently delete generated documents through normal UI operations.