# Matching Algorithm — Initial Design

Friendly will begin with a transparent rule-based recommendation system rather than artificial intelligence.

## Two-stage discovery

Location is a discovery filter, not a low-weight compatibility signal.

### Stage 1: establish the local discovery pool

A candidate is eligible only when:

1. their discoverable country matches the current user's active discovery country;
2. their discoverable city matches the current user's active discovery city;
3. they are open to connection;
4. they are not the currently logged-in user;
5. neither user has blocked the other when blocking is introduced.

The discovery location may differ from the user's home location.

### Stage 2: rank eligible candidates

Compatibility can then consider:

- shared languages;
- shared interests;
- connection intention;
- relocation or travel status;
- whether a local resident is open to welcoming newcomers;
- voluntarily supplied cultural preferences in a later version;
- overlapping availability dates in a future version.

Weights must be validated through product research and real usage rather than treated as permanent assumptions. Location should not receive points because it has already determined eligibility.

## Example

### Current user

- Home location: Cork, Ireland
- Active discovery location: Milan, Italy
- Intention: Travelling soon
- Languages: English, Ukrainian
- Interests: Cinema, coffee, art

### Eligible candidate

- Home location: Milan, Italy
- Active/discoverable location: Milan, Italy
- Intention: Local resident
- Open to welcoming newcomers: Yes
- Languages: Italian, English
- Interests: Cinema, museums, coffee

The candidate enters the pool because both users are discovering Milan and the candidate is open to connection. Shared English, cinema and coffee then affect ranking and recommendation explanations.

## Recommendation explanations

Friendly may explain recommendations with statements such as:

- You both speak English.
- You share two interests.
- You are both looking to connect in Milan.
- This person is a local resident open to welcoming newcomers.
- Your travel and connection intentions are compatible.

## Privacy and integrity

- Matching uses country and city, not live GPS or private addresses.
- Only voluntarily supplied profile information should affect ranking.
- Unsupported or missing location data must not silently place someone in another discovery pool.
- Ranking should be deterministic and testable for the MVP.
- Recommendation reasons must accurately reflect the underlying data.

## Future considerations

- optional availability windows;
- time-zone-aware plan and travel dates;
- user controls for distance beyond exact city matching;
- quality and safety signals that do not unfairly disadvantage new users;
- research-driven weight adjustments.
