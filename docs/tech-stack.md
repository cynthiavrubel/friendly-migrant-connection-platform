# Technology Stack

## Backend

- Python 3
- Flask
- Flask-SQLAlchemy
- Flask-Migrate and Alembic
- Flask-WTF and WTForms
- Werkzeug password hashing
- python-dotenv

## Database

- MySQL
- PyMySQL

MySQL stores normalized account, profile, location, language, interest and future Community Plan data. Flask-Migrate provides controlled, reviewable schema changes.

## Frontend

- Semantic HTML5
- Jinja templates
- Modern plain CSS
- Minimal vanilla JavaScript
- Inter with system-font fallbacks

Friendly deliberately avoids a frontend framework and build system at the current scale. Bootstrap, React, Vue, Tailwind, Node.js and npm are not part of the application stack.

## Development workflow

- Git and GitHub for version control
- Python virtual environment
- Environment variables for local secrets and database configuration
- Flask CLI for development and data-seeding commands

## Why this stack

### Flask

Flask supports a focused server-rendered architecture with explicit routing, validation and authorization. It keeps the MVP understandable while leaving room for APIs or additional clients later.

### MySQL and SQLAlchemy

The product requires relational integrity across users, locations, languages, interests, Community Plans and participants. SQLAlchemy provides expressive models while MySQL supplies durable relational storage.

### Server-rendered HTML and plain CSS

This approach provides fast pages, accessible forms and responsive interfaces without unnecessary client-side complexity. JavaScript is introduced only for interactions that genuinely require it.

## Europe-first technical considerations

- Store country and city separately.
- Use standardized country identifiers.
- Store plan timestamps consistently and render them in the appropriate location time zone.
- Keep text encoding at `utf8mb4` for multilingual names and content.
- Avoid architecture tied to Irish cities, one national locale or a single time zone.
- Do not require live GPS or private street addresses for discovery.
