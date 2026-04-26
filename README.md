# EATAL - Extenal Audit & Trust Assessment Layer

EATAL is a read-only governance tool that monitors OpenEMR break-glass/emergency patient-record access. It ingests audit logs, enriches events with clinician and encounter context, scores each access, and presents a risk-ranked review queue.

## System Description & Architecture Overview

EATAL is a six-module pipeline that lives entirely outside the OpenEMR boundary. It starts with Log Ingestion, which reads the OpenEMR audit log through a read-only SQL connection, while performing integrity checks. Next, in the Context Enrichment Module, it uses the audit logs from the Log Ingestion Module, reads users, facility, encounter, and calendar tables to acquire necessary contextual information for an access event. We then use all that data and put it through our Trust & Risk Scoring Engine, which calculates a trust score for each override event using four indicators: whether the provider was on/off shift, if it was a same-day encounter or within a configurable window encounter, temporal consistency, and peer override count. The next module is the Behavioral Drift Detection Module, which measures the ratio of break-glass overrides to standard access by department. It then does trend analysis for sustained increases that may indicate a general acceptance of break-glass access in that department.

## Installation



## Example inputs and expected outputs