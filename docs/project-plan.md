# Friendly Project Plan

## Product vision

Friendly is a Europe-first, global-ready community platform that helps newcomers, international residents, locals and travellers build meaningful local connections through shared languages, interests and Community Plans.

Ireland inspired the original idea. The MVP architecture must now support discovery across European countries and cities without assuming that a user's permanent location and current discovery location are the same.

## Target users

- People who recently relocated
- International residents building a local social circle
- Long-term and local residents open to new connections
- Temporary visitors
- People travelling soon who want to discover a destination in advance
- People seeking linguistic, cultural or interest-based connections

## Core problem

It is difficult to enter an existing social circle when moving or travelling. Formal event listings can help people find activities, but they do not necessarily show who is open to meeting someone new or make casual participation feel comfortable.

## Core solution

Friendly will:

- separate home location from active discovery location;
- use active country and city to establish the local discovery pool;
- recommend people who are open to connection;
- explain compatibility through shared languages, interests and intentions;
- let users create and join casual Community Plans;
- keep discovery location-based without collecting live GPS or exposing private addresses.

## MVP scope

### Accounts and profiles

1. Register, log in and log out securely.
2. Create and edit a profile.
3. Set a home country and city.
4. Set and change an active discovery country and city.
5. Select languages and interests.
6. Select a supported connection intention or relocation/travel status.
7. Indicate openness to connection.

### People discovery

1. Search the active country and city.
2. Exclude unavailable users and the current user.
3. Rank the remaining local candidates using transparent compatibility signals.
4. Explain why each person was recommended.

### Community Plans

1. Create a plan with country, city, title, category, description, date and time.
2. Set an optional capacity.
3. Browse plans by location.
4. View plan details.
5. Join or leave a plan.
6. Edit or cancel a plan created by the current user.
7. View plans the current user created or joined.

## MVP boundaries

The first MVP will not include:

- ticket purchasing or payments;
- live GPS or private-address discovery;
- real-time chat;
- recurring plans;
- calendar synchronization;
- private invitations;
- membership approval workflows;
- push notifications;
- native mobile applications;
- AI-generated recommendations.

## Technical goals

- Build with Python, Flask and MySQL.
- Model country and city explicitly for both home and active discovery locations.
- Use normalized relational data for languages, interests, plans and participation.
- Keep date/time storage ready for multiple European time zones.
- Support future optional travel availability dates without requiring them in the first profile release.
- Validate ownership and all user input server-side.
- Keep matching transparent and testable.
- Use migrations for controlled schema evolution.

## Delivery sequence

1. Authentication foundation
2. Europe-ready profile and dual-location model
3. Local people discovery and transparent matching
4. Community Plan creation and participation
5. Privacy, safety and moderation refinements
6. Deployment and product validation

Dates should be maintained in the active delivery tracker rather than hard-coded in this product document.
