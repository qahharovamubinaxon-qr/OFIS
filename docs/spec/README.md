# HR Document Automation System Pro

> Enterprise Windows Desktop Application for Automated Employment Document Processing

---

# Overview

HR Document Automation System Pro is a professional Windows desktop application designed for migration agencies, HR companies, staffing companies and employers who prepare employment document packages.

The software automatically reads employee documents using AI Vision + OCR, extracts required information, validates the extracted data and fills company PDF templates without Adobe Acrobat or Photoshop.

The application reduces document preparation time from approximately 15–20 minutes to under one minute.

---

# Main Goals

- Eliminate repetitive manual typing
- Reduce human errors
- Increase processing speed
- Support unlimited companies
- Automatically archive generated PDFs
- Build scalable enterprise software

---

# Main Features

## AI OCR

Read:

- Passport
- Patent
- Registration
- Migration Card

Extract all required information automatically.

---

## Smart Validation

Display editable form before PDF generation.

Operator can correct OCR mistakes.

---

## Company Templates

Unlimited companies.

Each company has its own PDF template.

All templates share identical field coordinates.

Only graphics and company information differ.

---

## Automatic PDF Generation

Fill every required field.

Generate final PDF.

Automatically save.

Automatically archive.

---

## Company Manager

Add Company

Edit Company

Delete Company

Archive Company

No source code modification required.

---

## Employee Archive

Search by

- Surname
- Passport Number
- Patent Number
- Company
- Date

---

## AI Providers

Supported

- Google Gemini
- OpenAI

Future

- Claude
- Azure OpenAI
- Local LLM

---

# Technology Stack

Python 3.12+

PySide6

SQLite

Pydantic

PyMuPDF

OpenCV

Pillow

Google Gemini API

OpenAI API

python-dotenv

PyInstaller

---

# Folder Structure

src/

ui/

controllers/

services/

ocr/

pdf/

database/

repositories/

models/

resources/

config/

utils/

tests/

templates/

archive/

output/

---

# Application Workflow

1. Launch application

2. Select company

3. Upload passport

4. Upload patent

5. Upload registration

6. Upload migration card

7. AI extracts information

8. User verifies extracted information

9. PDF is generated

10. PDF is archived automatically

---

# Architecture

The project follows Clean Architecture.

Presentation Layer

↓

Application Layer

↓

Domain Layer

↓

Infrastructure Layer

Every module must remain independent.

No business logic inside UI.

No OCR logic inside PDF engine.

No database logic inside UI.

---

# Coding Standards

- SOLID
- DRY
- KISS
- PEP8
- Type Hints
- Pydantic
- Dependency Injection
- Modular Design

---

# Performance Targets

Application startup

<3 seconds

OCR

<15 seconds

PDF generation

<3 seconds

Supports thousands of generated documents.

---

# Security

Encrypted API Keys

Validated inputs

Safe file handling

Graceful error handling

No sensitive information inside logs.

---

# Future Roadmap

Employee Database

Telegram Notifications

Patent Expiration Alerts

Registration Expiration Alerts

Cloud Backup

Auto Updates

Digital Signature

Excel Import

Excel Export

Word Export

Barcode

QR Code

Plugin System

Multi-user Support

Role Management

Cloud Synchronization

---

# Development Rules

Before implementing any feature:

- Analyze requirements.
- Design architecture.
- Create implementation plan.
- Build reusable modules.
- Write production-ready code.
- Test thoroughly.
- Commit only stable code.

Never create temporary hacks.

Never break existing functionality.

Never duplicate business logic.

Always maintain enterprise-level quality.