# Friendly Architecture

## Architectural direction

Friendly is a server-rendered Flask application backed by MySQL. The architecture should remain straightforward for the MVP while supporting multiple countries, cities and time zones without a later Ireland-specific data migration.

## Application layer

### Frontend

- Semantic HTML5 rendered with Jinja
- Modern plain CSS
- Minimal vanilla JavaScript where interaction requires it

Responsibilities include accessible forms, profile and discovery views, Community Plan interfaces, responsive layouts and clear validation feedback.

### Backend

- Python and Flask
- Flask-WTF for forms and CSRF protection
- Flask-SQLAlchemy for persistence
- Flask-Migrate/Alembic for controlled schema changes

Responsibilities include authentication, authorization, profile management, location selection, Community Plan ownership and participation, matching, validation and database transactions.

### Database

- MySQL accessed through PyMySQL
- Normalized relational tables
- Foreign keys, unique constraints and indexes for integrity

## Location architecture

City alone is not a sufficient location model. Location data must include country and city.

A user profile needs two distinct concepts:

1. **Home location** — the country and city where the user normally lives.
2. **Active discovery location** — the country and city where the user currently wants to find people and Community Plans.

The two locations may reference the same normalized location record but serve different purposes. A user must be able to change active discovery location without rewriting home location.

The model should avoid ambiguous free-text country values. Country codes should follow a consistent standard such as ISO 3166-1 alpha-2. City records should belong to a country and use stable identifiers where practical. Exact schema details require a decision on the geographic dataset or provider.

Friendly must not depend on exact live GPS and must not expose private addresses. Approximate city-level discovery is sufficient for the MVP.

## Conceptual data areas

- Users and authentication
- Profiles and connection intentions
- Countries and cities
- Home and active discovery locations
- Languages and profile languages
- Interests and profile interests
- Community Plans
- Plan participants

Community Plans require a country and city plus title, category, description, date, time, optional capacity, status and creator ownership. Participation needs a unique plan/user pair so the same user cannot join twice.

## Community Plan ownership

- Only authenticated users may create or join plans.
- Only a plan's creator may edit or cancel it.
- Joining and leaving must use transactional capacity checks.
- Cancellation should preserve enough data for participants to understand the plan status.
- Private addresses should not be required; a public meeting-place description can be considered separately with clear privacy guidance.

## Time and availability

Community Plan timestamps should be stored consistently—preferably in UTC—with the relevant location time zone available for display and validation.

Future profile architecture should allow optional availability start and end dates for travel discovery. These dates are not required in the first profile implementation.

## Matching boundary

The backend first filters candidates by active discovery country and city and openness to connection. It then ranks eligible candidates through shared languages, interests and compatible intentions. Matching must not treat city as merely another weighted score.

## Security and privacy

- Use server-side authorization for all ownership checks.
- Never accept user ownership identifiers without validating them against the authenticated user.
- Protect state-changing requests with CSRF.
- Store passwords only as secure hashes.
- Minimize collected location data.
- Do not store live GPS trails or expose private addresses.
- Validate plan capacity and participation at the database and transaction layers.

## Future expansion

The architecture may later support optional availability windows, broader distance discovery, moderation, messaging, notifications, mobile clients and improved recommendations. These should not complicate the initial MVP prematurely.
