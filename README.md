# LUMORA V6

Adds privacy-conscious visitor analytics to the LUMORA V5 Flask website.

## Visitor analytics
The admin panel now includes Visitor Analytics. It records public page views and interactions such as project/portfolio clicks, WhatsApp clicks, email clicks, external clicks and contact-form starts. The server records timestamp, path, referrer, browser user-agent, IP address and an anonymous visitor ID.

The system does not attempt to secretly extract a visitor's name, email or phone number. Those details are stored only when the visitor voluntarily submits the contact form; WhatsApp/email conversations are handled by those external services.

Analytics are available at Admin > Visitor Analytics.
