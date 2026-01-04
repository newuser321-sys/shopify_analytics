Agent Flow Description



1. The backend follows a controlled agent-style flow to answer user questions using store data.
2. The agent receives a user question along with a validated store\_id.
3. It inspects the locally available database schema to determine what data can be queried.
4. The agent uses an LLM to generate a SQL query based on the question and the schema.
5. The generated SQL is validated to ensure it is safe and syntactically correct.
6. If the question cannot be answered using the available data, the agent returns a graceful fallback response.
7. If valid, the SQL query is executed on the local SQLite database.
8. The query result is sent back to the LLM to generate a natural-language answer.
9. The final answer is returned to the Gateway server and then to the user.
10. This approach ensures that the LLM does not have direct access to Shopify APIs or raw data and operates only within controlled, validated tools.
