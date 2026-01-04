SHOPIFY MINI AI ANALYTICS — ARCHITECTURE OVERVIEW

This project follows a two-service architecture consisting of a Gateway Server and a Backend Server, designed to clearly separate authentication, security-sensitive operations, and AI/data processing.

1. Gateway Server (Auth & Request)

* The Gateway server is responsible for:
* Accepting user input (question and store_id)
* Managing Shopify authentication
* Acting as the only public-facing entry point
* When a request is received, the Gateway checks whether a valid access token exists for the given store_id.
* If the token is missing, the user is redirected through Shopify’s OAuth flow. Upon successful authentication, the access token is securely stored on the server.
* At no point is the access token exposed to the client or UI.
* Once authentication is complete, the Gateway forwards the validated request data to the Backend server for processing.

2. Backend Server (Data Processing \& AI Logic)

* The Backend server is responsible for:
* Validating incoming data from the Gateway
* Interacting with Shopify APIs
* Managing local data storage
* Handling all AI-related operations
* Using the authenticated access token, the Backend retrieves relevant Shopify store data via GraphQL and stores it in a local SQLite database. This local storage enables faster queries, reduced API usage, and controlled dataaccess for AI operations.

When a user question is received:

* The Backend provides the database schema to the LLM.
* The LLM generates a SQL query to retrieve the required data.
* The generated SQL is validated to prevent invalid or unsafe queries.
* If the required data does not exist, the system responds gracefully with an informative message.
* If valid, the SQL query is executed on the local database.
* The retrieved result is passed back to the LLM to generate a human-readable response.
* The final response is returned to the Gateway and then back to the user.

3. Architectural Benefits

* Security: Access tokens are never exposed beyond the backend boundary.
* Separation of concerns: Authentication, data access, and AI logic are isolated.
* Scalability: Gateway and Backend can be scaled independently.
* Reliability: External API calls and AI latency are isolated from the user-facing layer.
* Data safety: All LLM-generated SQL is validated before execution.
