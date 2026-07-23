# OCR ENGINE SPECIFICATION

Version 1.0

---

# PURPOSE

The OCR Engine is responsible for extracting structured information from employee documents.

The OCR Engine must never generate PDFs.

The OCR Engine must never communicate with the UI directly.

The OCR Engine returns validated structured data only.

---

# SUPPORTED DOCUMENTS

Passport

Patent

Registration

Migration Card

Future

Visa

Residence Permit

Work Permit

Insurance

Medical Certificate

SNILS

INN

---

# SUPPORTED INPUT

JPG

JPEG

PNG

WEBP

PDF

Multi-page PDF

TIFF

HEIC (Future)

---

# OCR PIPELINE

Upload Files

↓

Validate Files

↓

Detect Document Type

↓

Image Preprocessing

↓

AI Vision OCR

↓

JSON Extraction

↓

Normalization

↓

Validation

↓

Confidence Scoring

↓

Return Structured Models

---

# DOCUMENT TYPE DETECTION

Automatically detect

Passport

Patent

Registration

Migration Card

Unknown Document

Mixed Documents

Never ask the user to specify document type.

---

# IMAGE PREPROCESSING

Auto Rotate

Deskew

Perspective Correction

Noise Reduction

Contrast Enhancement

Brightness Adjustment

Sharpen

Background Cleaning

Border Cropping

Resolution Normalization

Color Normalization

---

# IMAGE VALIDATION

Reject

Unreadable images

Corrupted files

Zero-byte files

Unsupported formats

Very small images

Empty pages

Warn about

Blur

Low contrast

Overexposure

Underexposure

Partial document

---

# OCR PROVIDERS

Priority

1. Google Gemini Vision

2. OpenAI Vision

Future

Claude Vision

Azure Vision

AWS Textract

Google Document AI

Offline OCR

---

# PROVIDER FALLBACK

Primary Provider

↓

Failure

↓

Retry

↓

Secondary Provider

↓

Retry

↓

Return Error

Never silently ignore failures.

---

# OCR OUTPUT

The OCR Engine must return structured JSON.

Never return plain text.

Example

{
  "document_type": "passport",
  "confidence": 0.98,
  "fields": {
    "surname": "",
    "name": "",
    "passport_number": ""
  }
}

---

# CONFIDENCE SCORE

Each extracted field must include confidence.

Example

surname

0.99

passport_number

0.96

profession

0.82

Fields below configured threshold should be highlighted for manual review.

---

# FIELD NORMALIZATION

Normalize

Names

Dates

Passport Numbers

Patent Numbers

Whitespace

Unicode

Quotes

Hyphens

Letter Case

---

# DATE NORMALIZATION

Accept

DD.MM.YYYY

YYYY-MM-DD

DD/MM/YYYY

Convert to internal ISO format.

---

# NAME NORMALIZATION

Remove duplicate spaces.

Trim whitespace.

Preserve Cyrillic.

Preserve Latin.

Support Uzbek names.

Support Russian names.

---

# PASSPORT VALIDATION

Validate

Length

Characters

Format

Series

Number

Duplicate detection (optional)

---

# PATENT VALIDATION

Validate

Number

Profession

Issue Date

Expiration Date

Region

---

# REGISTRATION VALIDATION

Validate

Address

Registration Date

Expiration Date

---

# MIGRATION CARD VALIDATION

Validate

Number

Purpose

Entry Date

---

# MULTI-PAGE SUPPORT

Automatically merge

Front

Back

Multiple scans

Multiple PDF pages

Return one unified document model.

---

# RETRY STRATEGY

Temporary Error

↓

Retry

↓

Retry

↓

Switch Provider

↓

Retry

↓

Return Failure

Maximum retries configurable.

---

# ERROR TYPES

Invalid File

Unsupported Format

Unreadable Image

OCR Timeout

AI Timeout

Provider Error

Rate Limit

JSON Parse Error

Validation Failure

Unknown Error

---

# LOGGING

Store

Provider

Request Time

Response Time

Processing Duration

Confidence

Errors

Retries

Request ID

---

# PERFORMANCE

Single image

<5 seconds

Full employee package

<20 seconds

Batch processing supported.

---

# SECURITY

Never store API keys in source code.

Never expose raw provider responses to UI.

Sanitize all extracted text.

Validate every field before returning.

---

# FUTURE FEATURES

Batch OCR

Offline OCR

Handwriting Recognition

Barcode Detection

QR Code Detection

Face Extraction

Automatic Photo Cropping

Duplicate Employee Detection

Language Detection

Template Learning

---

# DEVELOPMENT RULES

OCR Engine must be provider-independent.

Switching providers must require configuration changes only.

Business logic must never depend on provider-specific responses.

All providers must return the same normalized internal models.

Every OCR result must be validated before leaving the OCR module.

The OCR Engine must remain reusable for future desktop, web, and cloud applications.