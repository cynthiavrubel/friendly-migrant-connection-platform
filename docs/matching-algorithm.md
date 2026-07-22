# Matching Algorithm – Initial Design

Friendly will calculate a compatibility score between the currently logged-in user and other users.

The MVP will use a transparent rule-based algorithm rather than artificial intelligence.

## Initial Scoring Rules

* 3 points for each shared interest
* 2 points if both users live in the same city
* 2 points for each shared language
* 1 point if both users are at a similar relocation stage
* 1 additional point if the candidate is happy to support newcomers and the current user recently arrived

## Example

### User A

* City: Cork
* Interests: Basketball, Reading, Technology
* Languages: English, Ukrainian
* Relocation stage: Recently arrived

### User B

* City: Cork
* Interests: Basketball, Technology, Cooking
* Languages: English, Ukrainian
* Relocation stage: Long-term resident
* Happy to support newcomers: Yes

## Score

* Two shared interests: 2 × 3 = 6 points
* Same city: 2 points
* Two shared languages: 2 × 2 = 4 points
* Newcomer support compatibility: 1 point

Total match score: 13 points

## Expected Behaviour

The application will:

1. Exclude the currently logged-in user
2. Retrieve other available user profiles
3. Calculate a compatibility score for every candidate
4. Sort candidates from highest to lowest score
5. Display the strongest matches first
6. Show the reasons behind each recommendation

## Recommendation Reasons

A user recommendation may display explanations such as:

* You both speak Ukrainian
* You both live in Cork
* You share two interests
* This user is happy to support newcomers
* You are both currently settling into Ireland

## Design Principle

The algorithm should be easy for users and recruiters to understand.

The weighting may be adjusted after testing the application with sample data.
