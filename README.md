# Replenishment Assistant (Demo)

A small demo of an AI agent that helps a **buyer** decide which raw materials
to reorder, and how much.

> **Everything in this project is fictional.** The company, suppliers,
> materials, prices and stock levels are all made up for demonstration
> purposes. No real business data is used.

## The scenario

**Hearthfield Foods** is a fictional mid-size food manufacturer that makes
baked goods and sauces. Its buyer manages dozens of raw materials, such as
flour, sugar, tomato paste, sunflower oil and packaging film.

Every week the buyer has to answer the same questions:

- Which materials are running low?
- Which ones will run out before a new delivery could arrive?
- How much should I order, and from which supplier?

The Replenishment Assistant looks at stock levels, daily usage, supplier lead
times and minimum order quantities, then suggests what to reorder and explains
why in plain language. The buyer stays in charge: the agent only makes
recommendations.

## How it works (planned)

```
  Dashboard (HTML/CSS/JS)  --->  API (FastAPI, Python)  --->  Data (JSON file)
        buyer clicks                works out what to          fictional stock,
        and reads results           reorder and explains why   usage and suppliers
```

1. **Data**: a JSON file holds the fictional materials, stock levels, average
   daily usage and supplier details.
2. **API**: a Python FastAPI app reads the JSON file, calculates how many days
   of stock are left for each material, and flags anything that needs
   reordering.
3. **Agent**: turns those numbers into clear recommendations, for example:
   "Order 2,000 kg of wheat flour from Millbrook Grain. Stock covers 4 days,
   but delivery takes 6."
4. **Dashboard**: a simple web page where the buyer sees the list of
   materials, their status, and the agent's suggestions.

## Tech stack

| Part      | Technology                   | Why                                   |
|-----------|------------------------------|---------------------------------------|
| API       | Python + FastAPI             | Simple, fast, auto-generated API docs |
| Data      | A JSON file                  | No database to set up                 |
| Dashboard | Plain HTML, CSS, JavaScript  | No build tools or frameworks needed   |

## Folder structure

```
replenishment-demo/
├── README.md        # This file: what the project is and how to run it
├── backend/         # Python code for the FastAPI app and the agent logic
├── data/            # The fictional JSON data the API reads
└── frontend/        # The HTML/CSS/JavaScript dashboard
```

## Status

This project is at the very start. So far there is only this README and the
empty folders above. Setup and run instructions will be added here as each
part gets built.

## Planned steps

- [x] Project description and folder structure
- [ ] Fictional data in `data/`
- [ ] FastAPI app in `backend/` that serves the data
- [ ] Reorder logic (days of stock left, reorder point, order quantity)
- [ ] Agent that explains its recommendations in plain language
- [ ] Dashboard in `frontend/`
