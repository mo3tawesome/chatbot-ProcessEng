import streamlit as st
import openai
import time
from io import BytesIO

# Set up Streamlit app
st.title("💬 Chatbot with Assistants API and Media Upload")
st.write(
    "This chatbot uses OpenAI's Assistants API and allows media upload. "
    "Please provide your OpenAI API key and Assistant ID below."
)

# Ask user for their OpenAI API key and Assistant ID via st.text_input.
openai_api_key = st.text_input("OpenAI API Key", type="password")
assistant_id = st.text_input("Assistant ID")

if not openai_api_key or not assistant_id:
    st.warning("Please enter both your OpenAI API Key and Assistant ID to continue.")
else:
    # Initialize OpenAI client
    from openai import OpenAI
    client = OpenAI(api_key=openai_api_key)

    # Initialize session state variables
    if "thread_id" not in st.session_state:
        # Create a new thread only once
        thread = client.beta.threads.create()
        st.session_state.thread_id = thread.id
    else:
        thread = client.beta.threads.retrieve(st.session_state.thread_id)

    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "last_message_id" not in st.session_state:
        st.session_state.last_message_id = None
    if 'last_uploaded_file_bytes' not in st.session_state:
        st.session_state['last_uploaded_file_bytes'] = None

    # Uploader and chat input fixed at the top
    st.write("### Send a Message:")
    uploaded_file = st.file_uploader("Upload an image", type=["png", "jpg", "jpeg"])
    prompt = st.chat_input("Type your message here...")

    # Chat container: Display messages below the input section
    chat_container = st.container()
    with chat_container:
        st.write("### Chat History:")
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                if message["role"] == "user" and message.get("is_image", False):
                    st.image(message["content"], caption="You")
                else:
                    st.markdown(message["content"])

    if prompt:
        message_content = []

        # Add user message to chat
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        message_content.append({"type": "text", "text": prompt})

        # Handle file upload
        if uploaded_file is not None:
            uploaded_file_bytes = uploaded_file.getvalue()

            # Check if the uploaded file is different from the last one
            if uploaded_file_bytes != st.session_state['last_uploaded_file_bytes']:
                image_bytes = uploaded_file_bytes

                # Create a file-like object for uploading
                uploaded_file_copy = BytesIO(uploaded_file_bytes)
                uploaded_file_copy.name = uploaded_file.name  # Set the file name

                # Upload the image via the Files API
                uploaded_image = client.files.create(
                    file=uploaded_file_copy,
                    purpose="vision"
                )
                image_file_id = uploaded_image.id

                # Add image to chat and session state
                st.session_state.messages.append({"role": "user", "content": image_bytes, "is_image": True})
                with st.chat_message("user"):
                    st.image(image_bytes, caption="You")

                # Send the image file ID to the assistant
                message_content.append({
                    "type": "image_file",
                    "image_file": {"file_id": image_file_id}
                })

                # Update the last uploaded file
                st.session_state['last_uploaded_file_bytes'] = uploaded_file_bytes
            else:
                # If the file is the same as before, do nothing
                pass

        # Send the user message to the assistant
        client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=message_content
        )

        # Get assistant response
        run = client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=assistant_id
        )

        # Wait for assistant response
        def wait_on_run(run, thread_id):
            while run.status in ["queued", "in_progress"]:
                time.sleep(1)
                run = client.beta.threads.runs.retrieve(
                    thread_id=thread_id,
                    run_id=run.id,
                )
            return run

        run = wait_on_run(run, st.session_state.thread_id)

        # Get messages from the assistant
        messages = client.beta.threads.messages.list(
            thread_id=st.session_state.thread_id,
            order='asc',
            after=st.session_state.last_message_id
        )

        # Update last_message_id
        if messages.data:
            st.session_state.last_message_id = messages.data[-1].id

        # Display assistant's response
        for message in messages.data:
            if message.role == "assistant":
                assistant_reply = ""
                for content_block in message.content:
                    if content_block.type == "text":
                        assistant_reply += content_block.text.value
                if assistant_reply:
                    with st.chat_message("assistant"):
                        st.markdown(assistant_reply)
                    st.session_state.messages.append({"role": "assistant", "content": assistant_reply})