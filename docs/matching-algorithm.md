# Matching Algorithm – Initial Design

Friendly will calculate a compatibility score between the current user and other users.

## Initial Scoring Rules

- 3 points for each shared interest
- 2 points if both users are in the same city
- 1 point for each shared language

## Example

User A:

- City: Cork
- Interests: Basketball, Reading, Technology
- Languages: English, Ukrainian

User B:

- City: Cork
- Interests: Basketball, Technology, Cooking
- Languages: English, French

Score:

- Two shared interests: 2 × 3 = 6 points
- Same city: 2 points
- One shared language: 1 point

Total match score: 9 points

## Expected Behaviour

The application will:

1. Exclude the currently logged-in user
2. Calculate a score for each candidate
3. Sort candidates from highest to lowest score
4. Display the strongest matches first
5. Show shared interests, languages or city as matching reasons

## Future Considerations

The weighting may be adjusted after testing.

The MVP will use a transparent rule-based algorithm rather than artificial intelligence.
