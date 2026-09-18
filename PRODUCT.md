# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Primary users are laboratory report staff who repeatedly create, review, regenerate, export, and audit regulated reports during desktop office work. System administrators also use the same authenticated application to manage templates, fields, users, permissions, and generation history.

## Product Purpose

The system turns LIMS records, Excel calculation workbooks, PDF spectra, protocol documents, and controlled templates into accurate, traceable Word reports. Success means staff can move a report from source selection to review and export without losing provenance or auditability.

## Positioning

Unlike a generic document dashboard, the product joins source recognition, standard-field mapping, Word template generation, evidence inspection, versioning, and audit history in one controlled report-production workflow.

## Operating Context

The product runs as a Vue 3 web application backed by FastAPI and MySQL. Staff work mainly on desktop and laptop screens, frequently search and filter report queues, handle exceptional states, and open a dedicated report workspace for detailed review.

## Capabilities and Constraints

- Role-based access controls every module and report action.
- Report sources remain separated by namespace and retain source evidence.
- Existing backend contracts, permissions, report actions, and creation workflow are authoritative.
- User-facing errors and system feedback are written in Chinese.
- The interface must remain usable from 1024px laptop widths through common desktop widths.
- New frontend dependencies require explicit approval.

## Brand Commitments

The product name is “报告自动生成系统” and the primary workspace is “智检报告系统”. The authenticated application should sit credibly alongside Feishu, DingTalk, and Amazon enterprise systems: restrained, operational, and free of decorative AI-interface styling.

## Evidence on Hand

- Existing production workflows and copy in `frontend/src/`.
- Existing institute logo at `frontend/src/assets/zbri-logo.png`.
- Real report, source, generation, and audit data supplied by the backend APIs.
- No testimonials, performance benchmarks, or commercial claims are available and none should be invented.

## Product Principles

- Put the next report action ahead of decorative summary content.
- Preserve data provenance, permissions, and auditability in every workflow.
- Make loading, failure, empty, and permission states explicit.
- Prefer compact, predictable controls that support repeated office work.
- Keep business rules and API access out of presentation components.

## Accessibility & Inclusion

Keyboard focus must remain visible, status must not rely on color alone, reduced-motion preferences must be respected, and Chinese labels must remain legible at supported desktop widths.
