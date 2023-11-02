import streamlit as st
from streamlit_option_menu import option_menu
import os
import subprocess
import pandas as pd
import matplotlib.pyplot as plt
import plotly.express as px
from datetime import datetime
import json
from azure.core.exceptions import ResourceNotFoundError
from azure.core.credentials import AzureKeyCredential
from azure.ai.formrecognizer import FormRecognizerClient
import mimetypes 
import pandas_bokeh

from google.cloud import firestore

# Initialize the Firestore client
def get_db():
    db = firestore.Client.from_service_account_json("key1.json")
    return db   

credentials = json.load(open('../credentials.json'))

API_KEY = credentials['API_KEY']
ENDPOINT = credentials['ENDPOINT']

form_recognizer_client = FormRecognizerClient(ENDPOINT,AzureKeyCredential(API_KEY))

st.write(
    """<style>
    .stButton {
        background-image: linear-gradient(to right, #00d2ff, #3a7bd5);
        color: black;
        padding: 10px 20px;
        text-align: center;
        text-decoration: none;
        font-size: 16px;
        cursor: pointer;
        border-radius: 8px;
        border: none;
        transition: background-color 0.5s;
    }
    .stButton:hover {
        background-color: #327fa8;
    }
    </style>""",
    unsafe_allow_html=True,
)


st.title("Receipts")

# Define a function to add data to Firestore
def add_data_to_firestore(img_path, bill_type, bill_date, bill_amount):
    db = get_db()
    doc_ref = db.collection("output_form").document()
    doc_ref.set({
        "img_path": img_path,
        "bill_type": bill_type,
        "bill_date": bill_date,
        "bill_amount": bill_amount
    })


# Define a function to run the external script
def run_receipt_script():
    csv_file = '../files/output_form.csv'
    if not os.path.isfile(csv_file):
        # Create an empty DataFrame to store the results
        df = pd.DataFrame(columns=['img_path', 'bill_type', 'bill_date', 'bill_amount'])
        df.to_csv(csv_file, index=False)
    else:
        # If the file exists, append the data to the DataFrame
        df = pd.read_csv(csv_file)

    folder_path = "../receipt_images/"

    processed_images = set(df['img_path'])

    
    progress_bar = st.progress(0)  # Create a progress bar object
    i = 0
    for filename in os.listdir(folder_path):
        if filename.lower().endswith((".jpg", ".jpeg", ".png")):
            img_path = os.path.join(folder_path, filename)

            if i < 100:
                i += 10
                progress_bar.progress(i)  # Progress to 10% done
            if img_path not in processed_images:
                with open(img_path, "rb") as image_file:
                    name = ""
                    total = 0
                    date = ""
                    content_type, _ = mimetypes.guess_type(img_path)

                    poller = form_recognizer_client.begin_recognize_receipts(image_file, content_type=content_type)

                    results = poller.result()

                    for receipt in results:
                        for name, field in receipt.fields.items():
                            if name == 'Total':
                                total = field.value
                            elif name == 'TransactionDate':
                                date = field.value
                            elif name == 'ReceiptType':
                                bill_type = field.value

                    # new_row = {'img_path': img_path, 'bill_type': bill_type, 'bill_date': date, 'bill_amount': total}
                    # df.loc[len(df)] = new_row
                    # processed_images.add(img_path)

                    # Add data to Firestore
                    add_data_to_firestore(img_path, bill_type, date, total)
                    processed_images.add(img_path)

    # save the df as a csv file
    df.to_csv('../files/output_form.csv', index=False)
    progress_bar.progress(100)  # Progress to 100% done
                

# Create a button to trigger the script execution
if st.button("Process"):
    
    info_placeholder = st.empty()  # Create an empty placeholder for dynamic text
    info_placeholder.info("Processing receipts...")

    run_receipt_script()
      # Progress to 100% done
    # Replace the message in the placeholder
    info_placeholder.success("Receipts processed and saved!")


# GENERATE INSIGHTS ============================================================

if st.button('Generate Insight'):
    import plotly.express as px

    df = pd.read_csv('../files/output_form.csv')
    # convert bill_date to datetime
    df['bill_date'] = pd.to_datetime(df['bill_date'])
    # Create a new column 'year-month'
    
    df['year-month'] = df['bill_date'].dt.strftime('%Y-%m')
    

    # Group by 'year-month' and calculate the sum of 'bill_amount'
    bill_totals_per_year_month = df.groupby('year-month')['bill_amount'].sum().reset_index()
    
    df1 = pd.DataFrame(bill_totals_per_year_month, columns=['year-month', 'bill_amount'])

    st.dataframe(df1, use_container_width=True)

    # Create the year-month line graph using Plotly Express
    fig = px.line(df1, x='year-month', y='bill_amount', markers=True)

    df1['year'] = df1['year-month'].str.split('-').str[0]
    df1['month'] = df1['year-month'].str.split('-').str[1]

    # st.dataframe(df1)

    # Customize the plot (optional)
    fig.update_layout(
        title='Year-Month Line Graph',
        xaxis_title='Year-Month',
        yaxis_title='Bill Amount',
        xaxis=dict(
            title_font=dict(size=25),  # Set x-axis title font size
            tickfont=dict(size=14),  # Set x-axis tick label font size
        ),
        yaxis=dict(
            title_font=dict(size=25),  # Set y-axis title font size
            tickfont=dict(size=14),  # Set y-axis tick label font size
        ),
        font=dict(size=32),
        width=400,  # Set the width of the plot
        height=300,  # Set the height of the plot
    )

    df2 = df1[['year','month', 'bill_amount']]
    df2 = df2.rename(columns={'year': 'Year','month':'Month', 'bill_amount': 'Bill Total'})

    # st.dataframe(df2)

    most_recent_years = df2['Year'].unique()[-4:]
    df_most_recent = df2[df2['Year'].isin(most_recent_years)]
    

    # Create the area plots
    fig2 = px.area(df_most_recent, x='Month', y='Bill Total', facet_col='Year', facet_col_wrap=2,
                color='Year',  # Use different colors for each year
                labels={'Bill Total': 'Bill Total'},  # Customize the label
                )  # Set a common title

    # Customize the Y-axis range for each graph
    for year in df_most_recent['Year'].unique():
        fig2.update_yaxes(range=[0, df_most_recent['Bill Total'].max()], row=df_most_recent['Year'].unique().tolist().index(year) + 1)

    # # Create the area plots for all years
    # fig2 = px.area(df2, x='Month', y='Bill Total', facet_col='Year', facet_col_wrap=2,
    #             color='Year',  # Use different colors for each year
    #             labels={'Bill Total': 'Bill Total'},  # Customize the label
    #             title='Yearly Area Plots')  # Set a common title

    # # Create a list of the most recent years (e.g., the last 3 years)
    # most_recent_years = df2['Year'].unique()[-3:]

    # # Define the facet sizes (large and small)
    # facet_sizes = [1.2 if year in most_recent_years else 0.8 for year in df2['Year'].unique()]

    # # Update the facet_col parameters to use the facet sizes
    # fig2.update_traces(facet_col=facet_sizes)
    fig2.update_layout(
    width=400,  # Set the width of the plot
    height=300,  # Set the height of the plot
    margin=dict(l=10, r=10, t=30, b=30)
    )




    # Increase font size and center-align text using HTML/CSS
    markdown_text = """
    <h2 style="text-align:center; font-size:30px;">Year-Month Line Graph</h2>
    """

    # Render the Markdown content
    st.markdown(markdown_text, unsafe_allow_html=True)
    st.plotly_chart(fig)
    # Add custom CSS styles
    st.markdown(
        """
        <style>
        .stApp {
            padding: 20px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
        # Increase font size and center-align text using HTML/CSS
    markdown_text = """
    <h2 style="text-align:center; font-size:30px;">Year Wise Expenditure</h2>
    """

    # Render the Markdown content
    st.markdown(markdown_text, unsafe_allow_html=True)
    st.plotly_chart(fig2)
