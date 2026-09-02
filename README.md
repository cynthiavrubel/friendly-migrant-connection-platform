# Friendly

Friendly helps newcomers, international residents, locals and travellers build meaningful local connections across Europe through shared languages, interests and Community Plans.

Ireland inspired the idea and remains Friendly's origin story. The product is now being architected as a Europe-first, global-ready platform rather than an Ireland-only service.

## About the product

Moving somewhere new—or arriving in a city for a short stay—can make it difficult to find people with whom everyday activities feel natural. Friendly is designed to make that first connection easier without becoming another follower-driven social network or dating application.

Users will be able to discover people in a selected city, understand what they have in common, and connect through casual user-created Community Plans such as coffee, a museum visit, a walk or a board-game evening.

## Product principles

- Local discovery without live GPS or private-address sharing
- Meaningful connections rather than endless scrolling
- Transparent recommendations based on voluntary profile information
- Support for permanent residents, recent arrivals, locals and travellers
- Europe-first location design that can expand globally
- Warm, accessible and privacy-conscious experiences

## Current completed features

- Responsive public landing page
- Account registration with server-side validation and CSRF protection
- Secure password hashing
- Login, session and logout flows
- Protected dashboard foundation
- MySQL database integration and controlled migrations
- Responsive authentication interfaces
- In-app activity centre for connections, messages and Community Plans

Profile, discovery and Community Plans functionality remains under active development and should not yet be treated as launched product functionality.

## Planned MVP capabilities

- Home country and city
- Active discovery country and city, independent of home location
- Connection intentions such as living locally, visiting or travelling soon
- Languages, interests and connection availability
- Location-filtered people discovery with transparent compatibility reasons
- User-created Community Plans
- Plan browsing and details by country and city
- Joining and leaving plans
- Editing or cancelling plans created by the current user
- Views for plans a user created or joined

The first MVP will not include payments, ticket purchasing, live GPS, real-time chat, recurring plans, calendar synchronization, private invitations, approval workflows or push notifications.

## In-app notifications

Friendly records successful connection requests and acceptances, new private-message activity, and Community Plan joins, leaves, removals and cancellations. These records are a derived activity history; Connections, Messages and Community Plans remain the source of truth. Unread message activity is coalesced to one notification per conversation until it is read. Opening or explicitly marking an item changes only notification read state, and destinations are derived from controlled notification types rather than stored URLs. Delivery is in-app on normal page loads only; email, push, real-time updates and preferences are not included.

## Community Plan timezones

Plan date/time input is interpreted as wall-clock time in the selected IANA timezone (for example, `Europe/Dublin`), then converted to UTC for storage and lifecycle comparisons. Plan cards, details, and edit forms convert that UTC instant back to the plan's own timezone. Nonexistent and duplicated local times during daylight-saving transitions are rejected with a form error rather than silently choosing an unintended instant. Browser timezone detection is a creation-form convenience only; server-side validation remains authoritative, and `Europe/Dublin` is the fallback when no supported browser hint is available. Existing Sprint 9 plans are migrated with `UTC`, preserving their original stored instant and display meaning.

## Technology stack

### Backend

- Python
- Flask
- Flask-SQLAlchemy
- Flask-Migrate
- Flask-WTF
- Werkzeug password hashing

### Frontend

- Semantic HTML5
- Modern plain CSS
- Minimal vanilla JavaScript

### Data and development

- MySQL
- PyMySQL
- Alembic migrations through Flask-Migrate
- Git and GitHub

## Project status

Friendly is under active development and is being prepared as a real product, not only as coursework or a demonstration project.

Current work is focused on reshaping profile and location architecture for the Europe-first direction before implementing people discovery and Community Plans.

## Design direction

Friendly should feel warm, welcoming, calm, modern, trustworthy and accessible. Its design philosophy draws inspiration from the clarity and restraint of products such as Airbnb, Notion and Stripe without copying their visual identity.

## Origin

Friendly began in Cork, Ireland, from the observation that relocation can be socially isolating even when a city is full of people and activities. That experience informs the product, but no longer limits who or where Friendly can support.

## Author

**Cynthia Vrubel**

Building Friendly as a production-minded software product and portfolio project.
