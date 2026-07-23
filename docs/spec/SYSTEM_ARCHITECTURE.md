# SYSTEM ARCHITECTURE

Version 1.0

---

# OBJECTIVE

The system must be built as an Enterprise Desktop Application using Clean Architecture.

Every module must be independent.

Every module must be replaceable.

Business logic must never depend on UI.

UI must never contain business logic.

Database must never communicate directly with UI.

All communication must pass through Services.

---

# HIGH LEVEL ARCHITECTURE

                User
                  │
                  ▼
          Presentation Layer
                  │
                  ▼
          Controller Layer
                  │
                  ▼
         Application Services
                  │
      ┌───────────┼────────────┐
      ▼           ▼            ▼
 OCR Service   PDF Service   Company Service
      │           │            │
      ▼           ▼            ▼
 AI Provider   PDF Engine   Database
      │
      ▼
 Gemini / OpenAI

---

# PROJECT STRUCTURE

src/

    app.py

    config/

    ui/

    controllers/

    services/

    database/

    repositories/

    models/

    ocr/

    ai/

    pdf/

    company/

    employee/

    archive/

    history/

    logging/

    utils/

    resources/

    tests/

---

# PRESENTATION LAYER

Responsible only for UI.

Contains

Windows

Dialogs

Buttons

Progress Bars

Tables

Themes

Icons

Translations

Never contains business logic.

---

# CONTROLLERS

Controllers receive UI events.

Example

Generate Button Clicked

↓

GenerateController

↓

calls

↓

OCRService

↓

ValidationService

↓

PDFService

↓

ArchiveService

Controller never processes data.

Controller only coordinates.

---

# SERVICES

Every feature is implemented as a Service.

Examples

OCRService

AIService

PDFService

CompanyService

ArchiveService

HistoryService

SearchService

UpdateService

SettingsService

BackupService

NotificationService

Services communicate with repositories.

Never with UI.

---

# REPOSITORIES

Repositories communicate only with SQLite.

Examples

CompanyRepository

EmployeeRepository

HistoryRepository

LogRepository

SettingsRepository

Repositories never call UI.

Repositories never call AI.

---

# MODELS

Every object is represented using Pydantic.

Example

Employee

Passport

Patent

Registration

MigrationCard

Company

GeneratedDocument

HistoryRecord

Settings

Every model must contain validation.

---

# OCR MODULE

Pipeline

Receive Images

↓

Detect Document Type

↓

Rotate

↓

Crop

↓

Noise Removal

↓

Contrast Enhancement

↓

Deskew

↓

AI Extraction

↓

JSON Validation

↓

Return Structured Data

OCR must never know about PDF.

OCR must never know about Database.

---

# AI MODULE

Responsibilities

Call Gemini

Call OpenAI

Normalize prompts

Validate response

Retry on failure

Convert AI response into Pydantic Models

Return validated objects

AI module must never access UI.

---

# PDF MODULE

Responsibilities

Load Template

Read Field Map

Insert Values

Generate PDF

Return File Path

Never communicate with OCR directly.

Receive validated models only.

---

# COMPANY MODULE

Responsibilities

Load company

Load template

Load logo

Load metadata

Create

Update

Delete

Archive

Import

Export

---

# EMPLOYEE MODULE

Responsibilities

Store employee information

Store OCR result

Store generated documents

Store history

Search

Update

Archive

---

# ARCHIVE MODULE

Responsibilities

Automatic folder creation

Year

Month

Company

Employee

Avoid duplicates

Generate unique names

---

# HISTORY MODULE

Store

Time

Company

Employee

Operator

OCR Duration

AI Duration

PDF Duration

Errors

Result

---

# SETTINGS MODULE

Language

Theme

AI Provider

Folders

Backup

Restore

Logging

Auto Update

---

# CONFIG MODULE

Application settings

Environment

API Keys

Constants

Folder locations

Feature flags

Never hardcode values.

---

# LOGGING MODULE

Log Levels

INFO

WARNING

ERROR

CRITICAL

Logs stored

Database

Log Files

Future

Remote Logging

---

# UTILITIES

Date Formatter

Image Helper

PDF Helper

Path Helper

Validation Helper

String Helper

File Helper

Hash Helper

---

# DATABASE FLOW

UI

↓

Controller

↓

Service

↓

Repository

↓

SQLite

Return

↓

Repository

↓

Service

↓

Controller

↓

UI

No shortcuts.

---

# OCR FLOW

Images

↓

OCR Service

↓

AI Service

↓

Validation

↓

Employee Model

↓

Controller

↓

UI

---

# PDF FLOW

Validated Employee

↓

PDF Service

↓

Template Loader

↓

Field Mapper

↓

PDF Generator

↓

Archive

↓

History

↓

UI

---

# DEPENDENCY RULES

UI

can access

Controllers

Controllers

can access

Services

Services

can access

Repositories

Repositories

can access

Database

Database accesses nothing.

Never break this rule.

---

# PLUGINS

Future support

OCR Provider

AI Provider

PDF Provider

Cloud Provider

Notification Provider

Each provider should be replaceable.

---

# ERROR FLOW

Exception

↓

Logger

↓

Friendly Error

↓

Recovery

↓

Continue Application

Application must never terminate unexpectedly.

---

# TESTING

Each Service must have unit tests.

Repositories must have integration tests.

PDF Engine must have output verification.

OCR Engine must have sample document tests.

UI should support manual testing.

---

# BUILD

Development

↓

Testing

↓

QA

↓

Release

↓

PyInstaller

↓

Single EXE

---

# SCALABILITY

Support

Unlimited companies

Unlimited templates

Unlimited employees

Unlimited generated PDFs

Support future cloud synchronization.

Support future multi-user mode.

Architecture must survive at least 10 years of future development.