import streamlit as st
import openai
import time
from io import BytesIO
import json
import re
import xml.etree.ElementTree as ET

# Set up Streamlit app
st.title("💬 AI Process Engineer")
st.write(
    "This chatbot uses OpenAI's Assistants API and performs process optimiaztion. "
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
        st.session_state.messages.append({"role": "user", "content": prompt, "is_json": False})
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
                st.session_state.messages.append({"role": "user", "content": image_bytes, "is_image": True, "is_json": False})
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
                    elif content_block.type == "json":
                        assistant_reply += json.dumps(content_block.json, indent=2)
                if assistant_reply:
                    with st.chat_message("assistant"):
                        st.markdown(assistant_reply)
                    st.session_state.messages.append({"role": "assistant", "content": assistant_reply, "is_json": False})

    # Button to transform the latest JSON object to XML using provided function and download it
    if st.button("View Latest JSON as a swimlane diagram"):
        # Find the latest JSON object in the chat history
        latest_json_message = None
        for message in reversed(st.session_state.messages):
            json_match = re.search(r'\{.*\}', message["content"], re.DOTALL)
            if json_match:
                try:
                    latest_json_message = json.loads(json_match.group())
                    break
                except json.JSONDecodeError:
                    continue

        if latest_json_message:
            # Use the provided function to transform the JSON into XML
            def transform_json_to_drawio_xml(data):
                diagram = ET.Element('mxfile')
                diagram_doc = ET.SubElement(diagram, 'diagram', name="Swimlane Diagram")
                graph_model = ET.SubElement(diagram_doc, 'mxGraphModel')
                root = ET.SubElement(graph_model, 'root')

                # Create root cells
                ET.SubElement(root, 'mxCell', id="0")
                ET.SubElement(root, 'mxCell', id="1", parent="0")

                # Create swimlanes and steps
                swimlane_ids = {}
                position_y = 0
                step_height = 60
                step_width = 150
                spacing = 20
                initial_offset = 50

                # Calculate total swimlane width dynamically
                max_column = max([position for position in range(len(data['arrows']) + 1)])
                swimlane_width = (max_column + 1) * (step_width + spacing) + initial_offset
                swimlane_height = 100

                total_timeline_height = 50 + 30

                # Create swimlanes
                for index, lane in enumerate(data['swimlanes'], start=2):
                    lane_id = f"lane_{index}"
                    swimlane_ids[lane['stakeholder']] = lane_id
                    lane_style = "swimlane;horizontal=0;whiteSpace=wrap;fillColor=#FFFFFF;swimlaneFillColor=default;"
                    lane_cell = ET.SubElement(root, 'mxCell', id=lane_id, parent="1", value=lane['stakeholder'], style=lane_style, vertex="1")
                    ET.SubElement(lane_cell, 'mxGeometry', y=str(position_y), width=str(swimlane_width), height=str(swimlane_height)).set('as', 'geometry')
                    position_y += swimlane_height

                # Add timeline swimlane
                timeline_id = "timeline"
                timeline_style = "swimlane;horizontal=0;whiteSpace=wrap;fillColor=#FFFFFF;swimlaneFillColor=default;"
                timeline_cell = ET.SubElement(root, 'mxCell', id=timeline_id, parent="1", value="Timeline", style=timeline_style, vertex="1")
                ET.SubElement(timeline_cell, 'mxGeometry', y=str(position_y), width=str(swimlane_width), height=str(total_timeline_height)).set('as', 'geometry')

                # Position steps in columns based on the order defined by arrows
                step_positions = {}
                current_column = 0
                column_width = step_width + spacing

                # Determine the order of steps based on arrows
                for arrow in data['arrows']:
                    from_id = arrow['from_id']
                    to_id = arrow['to_id']
                    if from_id not in step_positions:
                        step_positions[from_id] = current_column
                        current_column += 1
                    if to_id not in step_positions:
                        step_positions[to_id] = current_column
                        current_column += 1

                # Place steps in their respective swimlanes and columns
                for lane in data['swimlanes']:
                    for step in lane['steps']:
                        step_id = step['id']
                        swimlane_id = swimlane_ids[lane['stakeholder']]
                        color = "#00FF00"  # Default color if 'activity_type' is not present
                        if 'activity_type' in step:
                            color = "#00FF00" if step['activity_type'] == "value-adding" else "#FFFF00" if step['activity_type'] == "non-value-adding but necessary" else "#FF0000"
                        style = f"shape=rectangle;fillColor={color};strokeColor=#000000;whiteSpace=wrap;"
                        step_cell = ET.SubElement(root, 'mxCell', id=step_id, parent=swimlane_id, value=step['name'], style=style, vertex="1")
                        column_x = step_positions[step_id] * column_width + initial_offset
                        ET.SubElement(step_cell, 'mxGeometry', x=str(column_x), y=str(spacing), width=str(step_width), height=str(step_height)).set('as', 'geometry')

                        # Add time taken for each step in the timeline
                        timeline_step_id = f"timeline_{step_id}"
                        timeline_step_value = f"{step['time_taken_days']} days"
                        timeline_step_cell = ET.SubElement(root, 'mxCell', id=timeline_step_id, parent=timeline_id, value=timeline_step_value, vertex="1")
                        ET.SubElement(timeline_step_cell, 'mxGeometry', x=str(column_x), y=str(spacing), width=str(step_width), height=str(20)).set('as', 'geometry')

                # Add delay times between steps in the timeline
                for arrow in data['arrows']:
                    from_id = arrow['from_id']
                    to_id = arrow['to_id']
                    delay_time = arrow['delay_time']
                    if delay_time > 0:
                        from_column = step_positions[from_id]
                        to_column = step_positions[to_id]
                        delay_column_x = (from_column + to_column) / 2 * column_width + initial_offset
                        delay_id = f"delay_{from_id}_to_{to_id}"
                        delay_value = f"Delay: {delay_time} days"
                        delay_cell = ET.SubElement(root, 'mxCell', id=delay_id, parent=timeline_id, value=delay_value, vertex="1")
                        ET.SubElement(delay_cell, 'mxGeometry', x=str(delay_column_x), y=str(spacing + 30), width=str(step_width), height=str(20)).set('as', 'geometry')

                # Add arrows (connections)
                for arrow in data['arrows']:
                    from_id = arrow['from_id']
                    to_id = arrow['to_id']
                    arrow_style = "edgeStyle=elbowEdgeStyle;elbow=horizontal;orthogonalLoop=1;exitX=1;exitY=0.5;entryX=0;entryY=0.5;strokeColor=#000000;strokeWidth=2"
                    arrow_cell = ET.SubElement(root, 'mxCell', parent="1", edge="1", source=from_id, target=to_id, style=arrow_style)
                    ET.SubElement(arrow_cell, 'mxGeometry', relative="1").set('as', 'geometry')

                # Add process stats note
                process_stats = data['process_stats']
                process_stats_text = (
                    f"Cycle Time: {process_stats['cycle_time_days']} days\n"
                    f"Value-Adding Activities: {process_stats['time_value_adding_activities_days']} days\n"
                    f"Non-Value-Adding Activities: {process_stats['time_non_value_adding_activities_days']} days\n"
                    f"Value-Adding Percentage: {process_stats['value_adding_percentage']}%\n"
                    f"Non-Value-Adding Percentage: {process_stats['non_value_adding_percentage']}%\n"
                    f"Process Output: {process_stats['process_output_value']}\n"
                    f"Customer: {process_stats['customer']}"
                )
                process_stats_id = "process_stats"
                process_stats_cell = ET.SubElement(root, 'mxCell', id=process_stats_id, parent="1", value=process_stats_text, style="shape=note;whiteSpace=wrap;fillColor=#095bff;fontColor=#FFFFFF;", vertex="1")
                ET.SubElement(process_stats_cell, 'mxGeometry', x=str(swimlane_width + 20), y="20", width="300", height="200").set('as', 'geometry')

                return diagram

            xml_root = transform_json_to_drawio_xml(latest_json_message)
            xml_str = ET.tostring(xml_root, encoding='utf-8', method='xml')

            # Allow user to download the XML file
            st.download_button(
                label="Download diagrams.net File",
                data=xml_str,
                file_name="latest_message.xml",
                mime="application/xml"
            )
        else:
            st.warning("No JSON message found in chat history.")