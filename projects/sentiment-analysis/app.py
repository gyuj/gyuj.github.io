# September 1, 2025 Project of the Week: Sentiment Classifier
# https://gyuj.github.io/projects/sentiment-classifier/
# Utilizes streamlit, transformers, and huggingface to create a sentiment classifier

# importing streamlit and sns scraping - twitter
import streamlit as st
import snscrape.modules.twitter as sntwitter # web scrape tweets, had some errors 
import tweepy # requires twitter dev account

# huggingface transformers
from transformers import pipeline 

import pandas as pd
import matplotlib.pyplot as plt

# load in hugging face sentiment model (trained on about 124m tweets!) This is for gpu 
# sent_model = pipeline(
#     "sentiment-analysis", 
#     model="cardiffnlp/twitter-roberta-base-sentiment-latest",
#     device_map="auto",
#     trust_remote_code=True
# )

# load in hugging face model, using CPU for demo
sent_model = pipeline(
    "sentiment-analysis", 
    model="cardiffnlp/twitter-roberta-base-sentiment-latest",
    device=-1 # setting device to -1 for cpu
)

# twitter api dev acc--------------------------------
BEARER_TOKEN="AAAAAAAAAAAAAAAAAAAAAIz93wEAAAAAD7wQc%2BCobQ9nY9F3mrwLDHNMATY%3DvCUioLdoScPByG7GiG4smyTDgaQUqBYoQ44bGsFzbrfGIEKoDV"
client = tweepy.Client(BEARER_TOKEN)


# streamlit ui starts--------------------------------

# setting dashbaord title
st.set_page_config(page_title="sentiment dashboard", layout="wide")
st.title("Sentiment Analysis Dashboard")
st.write("this dashboard will allow you to gain social media sentiment analysis on **sports** or **financial items**")

# step 1: two options given to user
choice = st.radio("Choose a category: ", ["Sports", "Finance"])

# step 2: query based on input
if choice == "Sports":
    query = st.text_input("Enter a sports team or athlete you are curious about! (e.g. 'LeBron James', 'New York Yankees'):")
else:
    query = st.text_input("Enter a financial asset of your choice (e.g. 'AAPL', 'Bitcoin'):")

# step 3: run sentiment analysis
if st.button("Analyze Sentiment") and query:
    st.write(f"Analyzing sentiment for: {query}...~")

    tweet_texts = []

    # try load cached files first if exists
    cache_file = f"tweets_backup"



    try:
        # Pull 50 tweets with Tweepy
        tweets = client.search_recent_tweets(query=f"{query} lang:en", max_results=50)
        if not tweets.data:
            st.error("No tweets found for this query. Try something else.")
        else:
            tweet_texts = [t.text for t in tweets.data]
            st.success(f"Collected {len(tweet_texts)} tweets! Running sentiment analysis...")
    except Exception as e:
        st.error(f"Error fetching tweets: {e}")
    
    # Only run sentiment analysis if we have tweets
    if tweet_texts:
        try:
            # Run sentiment analysis
            sentiments = sent_model(tweet_texts)
            df = pd.DataFrame(sentiments)
            sentiment_counts = df['label'].value_counts(normalize=True) * 100

            # Display results
            st.write("--- Sentiment Analysis Results ---")
            st.write(sentiment_counts)

            # Pie chart visualization
            fig, ax = plt.subplots()
            sentiment_counts.plot(kind='pie', autopct='%1.1f%%', ax=ax)
            ax.set_ylabel('')
            st.pyplot(fig)
        except Exception as e:
            st.error(f"Error during sentiment analysis: {e}")