from telegram import Update, InputFile
import os
from google.cloud import speech_v1p1beta1 as speech
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from pydub import AudioSegment
import openai
openai.api_key = "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"

# Replace 'YOUR_API_TOKEN' with the API token you received from the BotFather
TOKEN = '6333318839:AAGCi43Z9JDRarEI-L8VmmodOoVxsuXAMNA'#greenybot


def start(update: Update, context: CallbackContext):
    update.message.reply_text("Hello! Send me an audio message or text message.")


def handle_audio(update: Update, context: CallbackContext):
    audio = update.message.voice
    if audio:
        print('audio')
        # Do something with the audio, such as saving it to a file or processing it
        # For this example, we'll just reply with the received audio
        update.message.reply_voice(audio)
    else:
        update.message.reply_text("Please send an audio message.")


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



def handle_text(update: Update, context: CallbackContext):
    text = update.message.text
    audio = update.message.voice
    if text:
        # Do something with the text message, such as processing it or generating a response
        # For this example, we'll just reply with the received text
        update.message.reply_text(f"You said: {text}")
    elif audio:
        if audio:
            # # Get the file_id of the audio
            # file_id = update.message.voice.file_id
            # # Get the File object from the bot using the file_id
            # audio_file = context.bot.get_file(file_id)
            # file_path = os.path.join("audio_files", f"{file_id}.m4a")
            # audio_file.download(file_path)
            # Download the audio file
            audio_file = audio.get_file()
            # audio_file_path = f"audio_{update.message.message_id}.m4a"  # Adjust the file name as needed
            audio_file_path = f"audio_{update.message.message_id}.mp3"
            # Save the audio file to your local machine
            audio_file.download(custom_path=audio_file_path)
            # update.message.reply_text(f"Audio received and saved as: {audio_file_path}")
            audio_file = open(audio_file_path, "rb")
            # transcript = openai.Audio.transcribe("whisper-1", audio_file)
            # print(transcript)
            transcript = transcribe_audio(audio_file_path)
            print("Transcription: ", transcript)
            # text = transcript["text"]
            update.message.reply_text(transcript)
            # update.message.reply_voice(audio)

    else:
        update.message.reply_text("Please send a text message.")


def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    # dp.add_handler(MessageHandler(Filters.voice, handle_audio))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command | Filters.voice, handle_text))

    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
