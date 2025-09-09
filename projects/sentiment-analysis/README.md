# Sentiment Classifier Dashboard  

## **Current status**
In progress:
Having demo prototype to work with Twitter API scraping, but running into issues. 

## Overview  
This project is an interactive **sentiment analysis dashboard** built with **Streamlit**.  
It allows users to analyze public sentiment on **sports teams/athletes** or **financial assets** by scraping recent tweets and applying a **pretrained Hugging Face transformer model**.  

## Goal  
The goal of this project is to provide a quick and intuitive way to measure how people feel about specific topics on Twitter, visualizing the distribution of positive, neutral, and negative sentiments.  

## Tools & Libraries  
- **Streamlit:** Building interactive dashboard.  
- **Transformers (Hugging Face):** Using the `cardiffnlp/twitter-roberta-base-sentiment-latest` model, trained on 124M tweets.  
- **Pandas & Matplotlib:** Data handling and visualization of sentiment results.  
- ~~**snscrape:**~~ For scraping tweets from Twitter. Replaced for instability.
- Different options for scraping data online: official Twitter API v2 with dev account/ Twint / Tweepy

## Features  
- Query-based tweet scraping (sports or finance).  
- Sentiment classification into **Positive, Neutral, Negative**.  
- Results displayed in both percentage breakdown and a **pie chart visualization**.  
- Easy-to-use UI for non-technical users.  

## How to Run  
1. Clone the repository.  
2. Install dependencies:  
   ```bash
   pip install -r requirements.txt
3. Run the Streamlit app:
   ```bash
   streamlit run app.py
