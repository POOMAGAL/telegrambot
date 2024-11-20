
import time
from collections import defaultdict
import openai
import logging
import gspread
import datetime
import re
from oauth2client.service_account import ServiceAccountCredentials
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, CallbackQueryHandler
from googleapiclient.discovery import build
from google.cloud import speech_v1p1beta1 as speech


# Enable logging to see any potential errors
# logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logging.basicConfig(filename='example.log', level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Replace 'YOUR_TOKEN' with the token you received from BotFather
TOKEN = '6139694889:AAGkI50Z__Gc6DebkP94NBm1wzV9LSoHyOg'# TL bot



# Replace 'YOUR_GOOGLE_SHEETS_CREDENTIALS_JSON_FILE' with the path to your credentials JSON file
GOOGLE_SHEETS_CREDENTIALS_FILE = 'credentials.json'


GOOGLE_SHEET_NAME = 'Thought_Leadership_Master'


# Initialize Google Sheets API credentials
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_SHEETS_CREDENTIALS_FILE, scope)
client = gspread.authorize(creds)

# Open the Google Sheet by name
sheet = client.open(GOOGLE_SHEET_NAME).sheet1

# Replace 'YOUR_OPENAI_API_KEY' with your actual OpenAI API key
# openai_api_key = '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' # our key
openai_api_key = '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' # Deepa key

# Set up the OpenAI API client
openai.api_key = openai_api_key

# A dictionary to store user registration status and details
registered_users = {}
registered_users_lst = []
conversation_history = {}
chat_ids_column = sheet.col_values(1)
registered_users_lst = chat_ids_column
article_details = {}
response_message = {}
first_statement = " I'm here to help you craft a wonderful piece of content. Let's get started. I'll ask you a series of questions to understand your needs better. Don't worry; it'll be a friendly chat! To start off, could you provide a rough working title or tell me the broad topic you have in mind?"

# To create a folder in Gdrive
def create_folder(name):
    parent_folder_id = '1Zm8WN65xPXbIAzhiEveFMxy3VKlN9MkF'  # Folder ID of "Thought leadership" folder
    drive_service = build('drive', 'v3', credentials=creds)
    folder_metadata = {
        'name': name,
        'mimeType': 'application/vnd.google-apps.folder'
    }
    if parent_folder_id:
        folder_metadata['parents'] = [parent_folder_id]
    folder = drive_service.files().create(body=folder_metadata, fields='id').execute()
    return folder.get('id')


# to open a new GS
def create_sheet(folder_name, parent_folder_id):
    drive_sheet = build('drive', 'v3', credentials=creds)
    file_metadata = {
        'name': f'Msg_log_{folder_name}',
        # 'name': folder_name,
        'mimeType': 'application/vnd.google-apps.spreadsheet',
    }
    if parent_folder_id:
        file_metadata['parents'] = [parent_folder_id]
    g_sheet = drive_sheet.files().create(body=file_metadata).execute()
    gs_id = g_sheet.get('id')

    # Once the spreadsheet is created, update the first row with column headers
    sheets_service = build('sheets', 'v4', credentials=creds)

    # Define the column headers
    column_headers = ["user_ID", "Time of message", "Message", "Response_URL"]

    # Update the first row with the column headers
    sheets_service.spreadsheets().values().update(
        spreadsheetId=gs_id,
        range='Sheet1',
        valueInputOption='RAW',
        body={'values': [column_headers]}
    ).execute()

    return gs_id


def create_doc(document_name, parent_folder_id):
    drive_service = build('drive', 'v3', credentials=creds)
    # folder_id = get_folder_id(folder_name)
    document_metadata = {
        # 'name': document_name,
        'name': f'GPT_log_{document_name}',
        'parents': [parent_folder_id],
        'mimeType': 'application/vnd.google-apps.document'
    }
    document = drive_service.files().create(body=document_metadata).execute()
    gd_id = document['id']
    return gd_id


def get_folder_id(folder_name):
    drive_service = build('drive', 'v3', credentials=creds)
    results = drive_service.files().list(
        q=f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder'",
        fields="files(id)").execute()
    items = results.get('files', [])
    if not items:
        raise ValueError("Folder not found.")
    return items[0]['id']


def append_response_to_document(document_id, message_content):
    # document_id = get_doc_id(document_name)
    docs_service = build('docs', 'v1', credentials=creds)

    # Retrieve the document content
    document = docs_service.documents().get(documentId=document_id).execute()
    # content = document.get('body').get('content')

    # Append the Chat GPT response to the document
    requests = [
        {
            'insertText': {
                'location': {
                    # 'index': len(content) - 1 if content else 1
                    'index': 1
                },
                'text': message_content + '\n'
            }
        }
    ]
    docs_service.documents().batchUpdate(documentId=document_id, body={'requests': requests}).execute()


# phone number validator
def is_valid_phone_number(phone_number):
    phone_number_pattern = r'^(\+\d{1,3}\s?)?(\(\d{1,}\))?[\s\d-]{10,}$'  # RE for phone number

    # re.match() function to check if the input matches the phone number pattern
    if re.match(phone_number_pattern, phone_number):
        return True
    else:
        return False


# check for valid mail ID
def is_valid_email(email):
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'  # RE for an email address

    # re.match() function to check if the input matches the email pattern
    if re.match(email_pattern, email):
        return True
    else:
        return False


def is_valid_name(name):
    # Regular expression to check for unwanted characters or spaces
    pattern = r'^[A-Za-z]+$'  # Allows only letters (upper and lower case)
    return re.match(pattern, name) is not None


def transcribe_audio(audio_file_path):
    client = speech.SpeechClient.from_service_account_json("search-console-digitalseo-cd50c58c171c.json")
    audio_file = open(audio_file_path, "rb")
    # with open(audio_file_path, "rb") as audio_file:
    content = audio_file.read()
    audio = speech.RecognitionAudio(content=content)
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.MP3,
        sample_rate_hertz=16000,
        language_code="en-US",
    )
    response = client.recognize(config=config, audio=audio)
    if len(response.results) > 0:
        transcript = response.results[0].alternatives[0].transcript
        return transcript
    else:
        return "No speech recognized."

# conversation_history = defaultdict(list)
def prompt_generator(user_id, gptresp, user_input, state):
    if user_id not in conversation_history:
        conversation_history[user_id] = []
    if state == 'audience':  # for forming audience question
        # first_qn = "what is the title of the article you want to write?"
        msg = f"{gptresp}" + ". " + f"{user_input}"
        conversation_history[user_id].append({"role": "system", "content": msg}, )
        conversation_history[user_id].append({"role": "assistant", "content": "Frame the next question to the user in a even more friendly way, asking about the primary audience for the content as points. Include recommended values as numbering points, so that user gets an idea."}, )
        message = gpt_response(user_id, conversation_history[user_id])
        return message
    if state == 'purpose':  # for forming purpose question
        msg = f"{gptresp}" + ". " + f"{user_input}"
        conversation_history[user_id].append({"role": "system", "content": msg}, )
        conversation_history[user_id].append({"role": "assistant", "content": "Remember the initial responses from the user, Frame the next question to the user with a callocial tone, asking about the purpose, objective or main goal of the article . Include recommended values as points, so that user gets an idea. "}, )
        message = gpt_response(user_id, conversation_history[user_id])
        return message
    if state == 'author':  # for forming author question
        msg = f"{gptresp}" + ". " + f"{user_input}"
        conversation_history[user_id].append({"role": "system", "content": msg}, )
        conversation_history[user_id].append({"role": "assistant", "content": "Remember the initial responses from the user, Frame the next question to the user in a conversational way, asking about the author of the article . Include recommended values as points, so that user gets an idea."}, )
        message = gpt_response(user_id, conversation_history[user_id])
        return message
    if state == 'publication':  # for forming publication question
        msg = f"{gptresp}" + ". " + f"{user_input}"
        conversation_history[user_id].append({"role": "system", "content": msg}, )
        # question for publication
        conversation_history[user_id].append({"role": "assistant", "content": "Remember the initial responses from the user, Frame the next question in such a friendly way to the user ,asking where the article has to be published? . Include recommended values as points, so that user gets an idea. "}, )
        message = gpt_response(user_id, conversation_history[user_id])
        return message
    if state == 'style':  # for forming writing style question
        msg = f"{gptresp}" + ". " + f"{user_input}"
        conversation_history[user_id].append({"role": "system", "content": msg}, )
        conversation_history[user_id].append({"role": "assistant", "content": "Remember the initial responses from the user, Frame the next question in such a conversational way to the user ,asking what will be preferred writing style of the article? . Include recommended values as points, so that user gets an idea. "}, )
        message = gpt_response(user_id, conversation_history[user_id])
        return message
    if state == 'language':  # for forming language style question
        msg = f"{gptresp}" + ". " + f"{user_input}"
        conversation_history[user_id].append({"role": "system", "content": msg}, )
        conversation_history[user_id].append({"role": "assistant",
                                     "content": "Remember the initial responses from the user, Frame the next question to the user ,asking what will be the preferred style of language for the article? . Include recommended values as points, so that user gets an idea. "}, )
        message = gpt_response(user_id, conversation_history[user_id])
        return message
    if state == 'keyword':  # for forming keywords question
        msg = f"{gptresp}" + ". " + f"{user_input}"
        conversation_history[user_id].append({"role": "system", "content": msg}, )
        conversation_history[user_id].append({"role": "assistant", "content": "Remember the initial responses from the user, Frame the next question to the user ,asking what are the keywords to be included during article generation? . Include recommended values as points, so that user gets an idea. "}, )
        message = gpt_response(user_id, conversation_history[user_id])
        return message


# def gpt_response(user_input):
#     MODEL = "gpt-3.5-turbo"
#     response = openai.ChatCompletion.create(
#         model=MODEL,
#         messages=user_input,
#         temperature=0,
#     )
#     processed_response = response['choices'][0]['message']['content']
#     return processed_response
def gpt_response(chat_id, user_input):
    print(user_input)
    user_details = sheet.findall(str(chat_id))
    message_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if user_details:
        user_name = sheet.cell(user_details[0].row, 4).value
        folder_name = f"{user_name}_{chat_id}"
        sheet_file_id = sheet.cell(user_details[0].row, 8).value
        doc_file_id = sheet.cell(user_details[0].row, 9).value
        # openai.api_key = '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'
        openai.api_key = openai_api_key
        MODEL = "gpt-3.5-turbo"
        # time.sleep(5)
        response = openai.ChatCompletion.create(
            model=MODEL,
            messages=user_input,
            temperature=0.5,
        )
        processed_response = response['choices'][0]['message']['content']
        response_message[chat_id] = processed_response
        # print(processed_response)
        # Format the processed information as a response message

        append_response_to_document(doc_file_id, f'{message_time}:bot reply:{response_message[chat_id]}\n')
        append_response_to_document(doc_file_id, f'{message_time}:user message:{user_input}\n')
        delimeter = "----------------------EOC-----------------------------------"
        append_response_to_document(doc_file_id, delimeter)
        row = [str(chat_id), message_time, user_input, f'https://docs.google.com/document/d/{doc_file_id}/edit']
        user_sheet = client.open_by_key(sheet_file_id)
        usersheet = user_sheet.sheet1
        # print(row)
        # usersheet.append_row(row)
        return response_message[chat_id]


# Handler function for the /start command
def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id

    if str(user_id) in registered_users_lst:
        update.message.reply_text("Hi, I am an automated content assistant bot. I will respond to the word 'article'")
    else:
        keyboard = [
            [InlineKeyboardButton("Yes", callback_data="yes"),
             InlineKeyboardButton("No", callback_data="no")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.message.reply_text("you are not registered yet. Do you want to register?", reply_markup=reply_markup)


# Handler function for processing callback data from inline buttons
def button_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    # print(query)
    user_id = query.from_user.id
    # user_id = update.effective_user.id

    if query.data == "yes":
        # User chose to register
        query.message.reply_text("User Id registered. please share other details. Enter your mail ID:")
        # query.message.edit_text("Please provide your details.\n\nEnter your mail ID:")
        registered_users[user_id] = {}
        registered_users_lst.append(str(user_id))
        registered_users[user_id]['state'] = 'mail'


    elif query.data == "no":
        # User chose not to register
        query.message.reply_text("Thanks for your response!")
    elif query.data == "callback_1":
        query = update.callback_query
        query.answer()
        # parameters = f"1.ARTICLE TITLE = {article_title}\n2.AUDIENCE = {target_audience}\n3.PURPOSE OF THE ARTICLE = {article_purpose}\n4.AUTHOR OF THE ARTICLE = {article_author}\n5.PUBLICATION = {publication}\n6.WRITING STYLE = {writing_Style}\n7.LANGUAGE STYLE= {article_language}\n8.KEYWORDS = {keywords}\n"
        # query.edit_message_text(text=f"{parameters}\nPlease type the corresponding number of the parameter to change")
        keyboard = [
            [InlineKeyboardButton("Article Title", callback_data='1')],
            [InlineKeyboardButton("Target Audience", callback_data='2')],
            [InlineKeyboardButton("Purpose", callback_data='3')],
            [InlineKeyboardButton("Author", callback_data='4')],
            [InlineKeyboardButton("Publication", callback_data='5')],
            [InlineKeyboardButton("writing style", callback_data='6')],
            [InlineKeyboardButton("Language", callback_data='7')],
            [InlineKeyboardButton("Keywords", callback_data='8')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        # Send a message with the inline keyboard
        query.edit_message_text("Choose a parameter to change", reply_markup=reply_markup)
    elif query.data == '1':
        article_details[user_id]['state']='title'
        query.edit_message_text("Kindly provide the fresh title for the article")
    elif query.data == '2':
        article_details[user_id]['state'] = 'audience'
        query.edit_message_text("Kindly provide the name of the new target audience")
    elif query.data == '3':
        article_details[user_id]['state']='purpose'
        query.edit_message_text("Kindly provide the revised objective for the article")
    elif query.data == '4':
        article_details[user_id]['state']='author'
        query.edit_message_text("Kindly provide the name of the new author for the article, if you would.")
    elif query.data == '5':
        article_details[user_id]['state']='publication'
        query.edit_message_text("Kindly provide the updated publication location for your article, if any.")
    elif query.data == '6':
        article_details[user_id]['state']='style'
        query.edit_message_text("Kindly provide the updated writing style you'd like for your article.")
    elif query.data == '7':
        article_details[user_id]['state']='language'
        query.edit_message_text("Kindly provide the other style of english in which your article has to be written.")
    elif query.data == '8':
        article_details[user_id]['state']='keyword'
        query.edit_message_text("Please enter the updated keywords for your article")

    elif query.data == "callback_2":
        query = update.callback_query
        query.answer()
        user_details = sheet.findall(str(user_id))
        article_details[user_id]['state'] = ''

        if user_details:
            mail_id = sheet.cell(user_details[0].row, 2).value
        # query.edit_message_text(text=f"We will process your content and send it to your registered email ID: {mail_id}")
        keyboard = [
            [InlineKeyboardButton("Yes, I wish to change the mail ID", callback_data='callback_3')],
            [InlineKeyboardButton("No, keep the same mail ID", callback_data='callback_4')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        # update.message.reply_text("Do you want to change the mail ID:", reply_markup=reply_markup)
        query.edit_message_text(text=f"We will process your content and send it to your registered email ID: {mail_id}, Do you want to change the mail ID?", reply_markup=reply_markup)
    elif query.data == "callback_3":
        query = update.callback_query
        query.answer()
        article_details[user_id]['state'] = 'mail'
        query.edit_message_text("Please enter your new mail ID")
    elif query.data == "callback_4":
        query = update.callback_query
        query.answer()
        # parameters = f"1.ARTICLE TITLE = {article_title}\n2.AUDIENCE = {target_audience}\n3.PURPOSE OF THE ARTICLE = {article_purpose}\n4.AUTHOR OF THE ARTICLE = {article_author}\n5.PUBLICATION = {publication}\n6.WRITING STYLE = {writing_Style}\n7.LANGUAGE STYLE= {article_language}\n8.KEYWORDS = {keywords}"
        # gpt_input = f"Consider you are an article writer. Write an article with the parameters as {parameters}"
        message = f"{article_details[user_id]['title']}\n{article_details[user_id]['audience']}\n {article_details[user_id]['purpose']} \n {article_details[user_id]['author']} \n {article_details[user_id]['publication']} \n {article_details[user_id]['style']} \n {article_details[user_id]['language']} \n {article_details[user_id]['keyword']}"
        query.edit_message_text(f"Process Initiated. Thank you . We will get in touch with you later on!\n {message}")
        # print(f"{article_title} \n {target_audience} \n{article_purpose} \n{article_author} \n{publication} \n{writing_Style} \n{article_language} \n{keywords}")
        print(f"{article_details[user_id]['title']}\n{article_details[user_id]['audience']}\n {article_details[user_id]['purpose']} \n {article_details[user_id]['author']} \n {article_details[user_id]['publication']} \n {article_details[user_id]['style']} \n {article_details[user_id]['language']} \n {article_details[user_id]['keyword']}")
        article_details[user_id]['title'] = ''
        article_details[user_id]['audience'] = ''
        article_details[user_id]['purpose'] = ''
        article_details[user_id]['author'] = ''
        article_details[user_id]['publication'] = ''
        article_details[user_id]['style'] = ''
        article_details[user_id]['language'] = ''
        article_details[user_id]['keyword'] = ''
        if user_id not in conversation_history:
            conversation_history[user_id] = []


def changes(update, context):

    keyboard = [
        [InlineKeyboardButton("Yes", callback_data='callback_1')],
        [InlineKeyboardButton("No", callback_data='callback_2')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Do you wish to change anymore parameters:", reply_markup=reply_markup)


def process_message(update: Update, context: CallbackContext):
    global registered_users_lst
    user_id = update.effective_user.id
    print(user_id)
    user_input = update.message.text
    print(user_input)
    state = article_details
    print(state)
    # registered_users_lst = sheet.col_values(1)
    chat_id = update.effective_chat.id
    user_input = update.message.text
    global first_statement, conversation_history, response_message
    if str(user_id) in registered_users_lst:
        if 'state' in registered_users.get(user_id, {}):
            # User is in the registration process, collect further details
            state = registered_users[user_id]['state']
            if state == 'mail':
                if is_valid_email(user_input):
                    # check for the input is valid mail ID
                    # Save mail ID and ask for the next detail
                    registered_users[user_id]['mail'] = update.message.text
                    update.message.reply_text("Enter your phone number:")
                    registered_users[user_id]['state'] = 'phone'
                else:
                    update.message.reply_text("Invalid Mail ID")
            elif state == 'phone':
                user_input_phone = update.message.text
                if is_valid_phone_number(user_input_phone):
                    # Save phone number and ask for the next detail
                    registered_users[user_id]['phone'] = update.message.text
                    update.message.reply_text("Enter your name:")
                    update.message.reply_text("Name must not contain any special characters or spaces.")
                    registered_users[user_id]['state'] = 'name'
                else:
                    update.message.reply_text("Invalid number")
            elif state == 'name':
                user_input_name = update.message.text
                if is_valid_name(user_input_name):
                    # Save name and ask for the next detail
                    registered_users[user_id]['name'] = update.message.text
                    update.message.reply_text("Enter your designation:")
                    registered_users[user_id]['state'] = 'designation'
                else:
                    update.message.reply_text("Name must not contain any special characters or spaces.")
            elif state == 'designation':
                # Save designation and ask for the next detail
                registered_users[user_id]['designation'] = update.message.text
                update.message.reply_text("Enter your company name:")
                registered_users[user_id]['state'] = 'company'
            elif state == 'company':
                # Save company name and finish registration
                registered_users[user_id]['company'] = update.message.text
                user_name = registered_users[user_id]['name']
                folder_name = f"{user_name}_{user_id}"
                new_folder_id = create_folder(folder_name)
                if new_folder_id:
                    print(f"New folder {folder_name} created")
                    gs_id = create_sheet(folder_name, new_folder_id)
                    gd_id = create_doc(folder_name, new_folder_id)
                    print(f"A GSheet and GDoc is created for the user {folder_name}")
                    # Save user details to Google Sheets
                row_values = [
                    str(user_id),
                    registered_users[user_id]['mail'],
                    registered_users[user_id]['phone'],
                    registered_users[user_id]['name'],
                    registered_users[user_id]['designation'],
                    registered_users[user_id]['company'],
                    new_folder_id,
                    gs_id,
                    gd_id
                ]
                sheet.append_row(row_values)

                del registered_users[user_id]['state']
                update.message.reply_text("You are Successfully Registered! Thank you.")
                update.message.reply_text("Hi, I am an automated content assistant bot. I will respond to the word 'article'?")
        elif 'state' in article_details.get(user_id, {}):
            state = article_details[user_id]['state']
            print(state)
            if state == '':
                update.message.reply_text("I am an automated content assistant bot. I will respond to the word 'article'")
            if state == '' and user_input.lower() == 'article':
                print("state is assigned to null")
                article_details[user_id] = {}
                article_details[user_id]['state'] = 'title'
                article_details[user_id]['title'] = ''
                update.message.reply_text("🌟 I'm here to help you craft a wonderful piece of content. Let's get started. I'll ask you a series of questions to understand your needs better. Don't worry; it'll be a friendly chat! To start off, could you provide a rough working title or tell me the broad topic you have in mind? \nIn between if you want to exit the process or to restart, type 'EXIT'")
            elif user_input.lower() == 'exit':
                # message = f"{article_details[user_id]['title']}\n{article_details[user_id]['audience']}\n {article_details[user_id]['purpose']} \n {article_details[user_id]['author']} \n {article_details[user_id]['publication']} \n {article_details[user_id]['style']} \n {article_details[user_id]['language']} \n {article_details[user_id]['keyword']}"
                update.message.reply_text(f"Thank you. All your current responses have been captured")
                article_details[user_id]['state'] = ''
            elif state == 'title':
                # if user_id in article_details and 'title' in article_details[user_id] and not article_details[user_id]['title']:
                if user_id in article_details and 'state' in article_details[user_id] and article_details[user_id]['state'] == 'title':
                    if article_details[user_id]['title'] == '':
                        article_details[user_id]['title'] = update.message.text
                        article_details[user_id]['state'] = 'audience'
                        article_details[user_id]['audience'] = ''
                        state = article_details[user_id]['state']
                        if state == 'audience':
                            response_message[user_id] = prompt_generator(user_id,first_statement,user_input,state)
                            update.message.reply_text(response_message[user_id])
                    else:
                        article_details[user_id]['title'] = update.message.text
                        update.message.reply_text("Article Title is Updated")
                        changes(update, context)
            elif state == 'audience':
                if user_id in article_details and 'state' in article_details[user_id] and article_details[user_id]['state'] == 'audience':
                    if article_details[user_id]['audience'] == '':
                        article_details[user_id]['audience'] = update.message.text
                        article_details[user_id]['state'] = 'purpose'
                        article_details[user_id]['purpose'] = ''
                        state = article_details[user_id]['state']
                        if state == 'purpose':
                            response_message[user_id] = prompt_generator(user_id,response_message[user_id], user_input, state)
                            update.message.reply_text(response_message[user_id])
                    else:
                        article_details[user_id]['audience'] = update.message.text
                        update.message.reply_text("Target Audience is Updated")
                        changes(update, context)
            elif state == 'purpose':
                if user_id in article_details and 'state' in article_details[user_id] and article_details[user_id]['state'] == 'purpose':
                    if article_details[user_id]['purpose'] == '':
                        article_details[user_id]['purpose'] = update.message.text
                        article_details[user_id]['state'] = 'author'
                        article_details[user_id]['author'] = ''
                        state = article_details[user_id]['state']
                        if state == 'author':
                            response_message[user_id] = prompt_generator(user_id, response_message[user_id], user_input, state)
                            update.message.reply_text(response_message[user_id])
                    else:
                        article_details[user_id]['purpose'] = update.message.text
                        update.message.reply_text("Purpose of the Article is Updated")
                        changes(update, context)
            elif state == 'author':
                if user_id in article_details and 'state' in article_details[user_id] and article_details[user_id]['state'] == 'author':
                    if article_details[user_id]['author'] == '':
                        article_details[user_id]['author'] = update.message.text
                        article_details[user_id]['state'] = 'publication'
                        article_details[user_id]['publication'] = ''
                        state = article_details[user_id]['state']
                        if state == 'publication':
                            response_message[user_id] = prompt_generator(user_id, response_message[user_id], user_input, state)
                            update.message.reply_text(response_message[user_id])
                    else:
                        article_details[user_id]['author'] = update.message.text
                        update.message.reply_text("Author of the article is Updated")
                        changes(update, context)
            elif state == 'publication':
                if user_id in article_details and 'state' in article_details[user_id] and article_details[user_id]['state'] == 'publication':
                    if article_details[user_id]['publication'] == '':
                        article_details[user_id]['publication'] = update.message.text
                        article_details[user_id]['state'] = 'style'
                        article_details[user_id]['style'] = ''
                        state = article_details[user_id]['state']
                        if state == 'style':
                            response_message[user_id] = prompt_generator(user_id, response_message[user_id], user_input, state)
                            update.message.reply_text(response_message[user_id])
                    else:
                        article_details[user_id]['publication'] = update.message.text
                        update.message.reply_text("Your publication is Updated")
                        changes(update, context)
            elif state == 'style':
                if user_id in article_details and 'state' in article_details[user_id] and article_details[user_id]['state'] == 'style':
                    if article_details[user_id]['style'] == '':
                        article_details[user_id]['style'] = update.message.text
                        article_details[user_id]['state'] = 'language'
                        article_details[user_id]['language'] = ''
                        state = article_details[user_id]['state']
                        if state == 'language':
                            response_message[user_id] = prompt_generator(user_id, response_message[user_id], user_input, state)
                            update.message.reply_text(response_message[user_id])
                    else:
                        article_details[user_id]['style'] = update.message.text
                        update.message.reply_text("Your writing style is Updated")
                        changes(update, context)
            elif state == 'language':
                if user_id in article_details and 'state' in article_details[user_id] and article_details[user_id]['state'] == 'language':
                    if article_details[user_id]['language'] == '':
                        article_details[user_id]['language'] = update.message.text
                        article_details[user_id]['state'] = 'keyword'
                        article_details[user_id]['keyword'] = ''
                        state = article_details[user_id]['state']
                        if state == 'keyword':
                            response_message[user_id] = prompt_generator(user_id, response_message[user_id], user_input, state)
                            update.message.reply_text(response_message[user_id])
                    else:
                        article_details[user_id]['language'] = update.message.text
                        update.message.reply_text("Your language style is Updated")
                        changes(update, context)
            elif state == 'keyword':
                if user_id in article_details and 'state' in article_details[user_id] and article_details[user_id]['state'] == 'keyword':
                    if article_details[user_id]['keyword'] == '':
                        article_details[user_id]['keyword'] = update.message.text
                        keyboard = [
                            [InlineKeyboardButton("Yes", callback_data='callback_1')],
                            [InlineKeyboardButton("No", callback_data='callback_2')]
                        ]
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        update.message.reply_text("Do you wish to change the parameters you recently entered for article generation:", reply_markup=reply_markup)
                    else:
                        article_details[user_id]['keyword'] = update.message.text
                        update.message.reply_text("Your keywords are Updated")
                        changes(update, context)
            elif state == 'mail':
                if is_valid_email(user_input):
                    article_details[user_id]['mail'] = update.message.text
                    user_details = sheet.findall(str(chat_id))
                    if user_details:
                        sheet.update_cell(user_details[0].row, 2, user_input)
                        message = f"{article_details[user_id]['title']}\n{article_details[user_id]['audience']}\n {article_details[user_id]['purpose']} \n {article_details[user_id]['author']} \n {article_details[user_id]['publication']} \n {article_details[user_id]['style']} \n {article_details[user_id]['language']} \n {article_details[user_id]['keyword']}"
                        update.message.reply_text(f"Mail ID is updated and the Process Initiated. Thank you . We will get in touch with you later on! \n {message}")
                        print(f"{article_details[user_id]['title']}\n{article_details[user_id]['audience']}\n {article_details[user_id]['purpose']} \n {article_details[user_id]['author']} \n {article_details[user_id]['publication']} \n {article_details[user_id]['style']} \n {article_details[user_id]['language']} \n {article_details[user_id]['keyword']}")
                        article_details[user_id]['state'] = ''
        elif user_input.lower() == 'article':
            print("only article, not state assinged")
            article_details[user_id] = {}
            article_details[user_id]['state'] = 'title'
            article_details[user_id]['title'] = ''
            print("state assigned as title and title  value is updated to null")
            update.message.reply_text("🌟 I'm here to help you craft a wonderful piece of content. Let's get started. I'll ask you a series of questions to understand your needs better. Don't worry; it'll be a friendly chat! To start off, could you provide a rough working title or tell me the broad topic you have in mind?\nIn between if you want to exit the process or to restart, type 'EXIT'")
        else:
            update.message.reply_text("Hi, I am an automated content assistant bot. I will respond to the word 'article'")

    else:
        # User is not registered and not in the process of registration
        # Prompt user to register
        keyboard = [
            [InlineKeyboardButton("Yes", callback_data="yes"),
             InlineKeyboardButton("No", callback_data="no")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.message.reply_text("Do you want to register?", reply_markup=reply_markup)



# Create an updater object to interact with Telegram Bot API
updater = Updater(token=TOKEN, use_context=True)
dispatcher = updater.dispatcher

dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CallbackQueryHandler(button_callback))
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command | Filters.voice, process_message))
# dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, process_message))

# Start the bot
updater.start_polling()
updater.idle()

