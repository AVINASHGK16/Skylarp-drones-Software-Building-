# Skylarp Business Intelligence Agent
## Engineering Decision Log

**Author:** Avinash G K  
**Project:** Executive Business Intelligence Agent  
**Version:** 1.0  
**Status:** Production Deployment Complete

---

# Purpose

This document captures the major technical decisions, architectural choices, trade-offs, deployment strategy, and provider migration decisions made during development.

The objective of the project was to build a Business Intelligence platform capable of:

- Processing structured business data
- Computing executive KPIs
- Producing strategic insights using an LLM
- Maintaining a clean separation between deterministic analytics and AI reasoning
- Deploying the solution to production

---

# High-Level Architecture

```
                 React + Vite Frontend
                         │
                         │ REST API
                         ▼
                  FastAPI Backend
                         │
        ┌────────────────┼────────────────┐
        │                │                │
        ▼                ▼                ▼
 Data Cleaner     Analytics Engine    BI Agent
        │                │                │
        └────────────┬───┘                │
                     ▼                    ▼
            Structured Metrics       Groq LLM API
```

---

# Decision 1 — FastAPI as Backend Framework

## Alternatives Considered

- Flask
- Django
- FastAPI

## Decision

Use **FastAPI**

## Rationale

FastAPI provides:

- Automatic OpenAPI documentation
- High performance
- Async support
- Request validation using Pydantic
- Minimal boilerplate

The automatic Swagger documentation was particularly useful during deployment and debugging.

---

# Decision 2 — React + Vite

## Alternatives

- React + CRA
- Next.js
- React + Vite

## Decision

React + Vite

## Reasoning

Vite offers

- faster startup
- faster HMR
- smaller configuration
- lightweight production builds

Since the application behaves as a dashboard instead of an SSR application, Vite was the most suitable choice.

---

# Decision 3 — Layered Architecture

The application was intentionally separated into independent responsibilities.

## Analytics Engine

Responsible only for

- KPI calculation
- aggregation
- business metrics
- dashboards

No AI logic exists here.

---

## BI Agent

Responsible only for

- strategic reasoning
- executive summaries
- business recommendations
- answering natural language questions

No mathematical calculations are performed by the AI.

---

## Data Cleaner

Responsible for

- missing values
- invalid dates
- inconsistent categories
- numeric normalization

Cleaning occurs before analytics.

This prevents downstream failures.

---

# Decision 4 — AI Should Never Calculate Business Metrics

One major design decision was separating deterministic analytics from AI reasoning.

Instead of asking the LLM:

> "Calculate pipeline value."

the Analytics Engine calculates

- pipeline value
- conversion rate
- revenue
- completion rate

The BI Agent receives those values as context and explains them.

Advantages:

- reproducible calculations
- deterministic results
- easier testing
- reduced hallucination

---

# Decision 5 — AI Provider Abstraction

The project isolates all LLM communication inside

```
backend/services/bi_agent.py
```

No other module communicates directly with the AI provider.

Benefits

- easy provider replacement
- centralized prompts
- centralized error handling
- reduced coupling

---

# Decision 6 — Gemini → Groq Migration

## Original Provider

Google Gemini API

### Why Gemini?

Initially selected because

- generous free tier
- official SDK
- good reasoning capability

---

## Problem Encountered

During deployment the project experienced

- 404 model availability differences
- API version incompatibilities
- Free-tier quota exhaustion
- deployment instability

The application itself remained healthy but external quota restrictions prevented reliable demonstrations.

---

## Final Decision

Migrate to Groq.

---

## Why Groq?

Groq provides

- OpenAI-compatible interface
- free developer tier
- high inference speed
- minimal migration effort

Because the application isolated provider-specific logic, only the BI Agent required modification.

No REST endpoints changed.

No frontend changes were required beyond labels.

---

# Decision 7 — Error Handling Strategy

Errors are categorized into

## Data Errors

Handled by Data Cleaner.

Examples

- null values
- invalid dates
- malformed numeric fields

---

## AI Provider Errors

Handled inside BI Agent.

Examples

- quota exceeded
- invalid credentials
- provider unavailable

User receives

> "The AI service has reached its usage quota."

instead of raw exceptions.

---

## Backend Errors

Handled by FastAPI exception handling.

Application remains operational whenever possible.

---

# Decision 8 — Deployment Strategy

Frontend

Hosted on

- Vercel

Reasons

- automatic GitHub deployment
- CDN
- HTTPS
- simple React deployment

---

Backend

Hosted on

- Render

Reasons

- FastAPI support
- automatic deployment
- environment variable management

---

# Decision 9 — Environment Variables

Frontend

```
VITE_API_URL
```

Backend

```
GROQ_API_KEY
ALLOWED_ORIGINS
```

Sensitive credentials are never committed.

---

# Decision 10 — Git Workflow

Development followed

```
Feature

↓

Local Testing

↓

Commit

↓

Push

↓

Automatic Deployment

↓

Production Verification
```

---

# Testing Strategy

The following components were verified

✔ REST endpoints

✔ BI Agent

✔ Analytics

✔ Dashboard metrics

✔ Deployment

✔ API connectivity

✔ Environment variables

---

# Major Challenges Encountered

## Challenge 1

OpenAI API billing restrictions

### Resolution

Migrated to Gemini.

---

## Challenge 2

Gemini model availability

Different API keys exposed different model versions.

### Resolution

Implemented dynamic model discovery.

---

## Challenge 3

Gemini quota exhaustion

Production deployment exceeded free-tier quota.

### Resolution

Migrated to Groq using OpenAI-compatible interface.

---

## Challenge 4

Backend deployment

Resolved

- CORS
- Render configuration
- environment variables
- production startup

---

# Lessons Learned

This project reinforced several engineering principles.

## Separation of Concerns

Analytics and AI reasoning should remain independent.

---

## Provider Independence

AI providers change.

Applications should isolate provider-specific code.

---

## Graceful Failure

External AI failures should never crash the application.

---

## Deployment Matters

A working production deployment is as important as working local code.

---

# Future Improvements

- Streaming AI responses
- Authentication
- Role-based dashboards
- Database persistence
- Caching
- Prompt versioning
- Conversation memory
- Monitoring
- Unit test expansion
- CI/CD pipeline

---

# Final Outcome

Successfully delivered

- Executive BI dashboard
- Analytics engine
- AI-powered business assistant
- Production-ready REST API
- React frontend
- FastAPI backend
- Automated deployment
- AI provider abstraction
- Groq-based production inference

Despite external API quota limitations during development, the architecture allowed rapid provider migration with minimal code changes, validating the effectiveness of the layered design.

---

**Final Status**

**Project Successfully Completed**
