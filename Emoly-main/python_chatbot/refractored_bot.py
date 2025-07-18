#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Apr 18 16:59:22 2025
@author: shivanikandhai
A therapeutic chatbot named Aire with multi-phase emotion regulation.
Features:
- Fuzzy endphase() detection
- Emotion recognition via Plutchik’s Wheel with JSON output
- Trigger extraction and clinician prompt
- Strategy decision using Extended Process Model & reappraisal subtype
- Phases 1–3 guided by WPVA, implementation, and reflection
- Gemini summaries for each phase
"""

from flask import Flask, request, jsonify
import os
import sys
import difflib
import json
import datetime
from zoneinfo import ZoneInfo
from openai import OpenAI
import google.generativeai as genai
from sqlalchemy.orm import Session
from sqlalchemy import func 
from data_base import SessionLocal, Intervention, BiometricData 
import numpy as np
import tensorflow as tf

def calculate_hrv_features(ibi_series):
    """
    Calculates HRV features from a series of Inter-Beat Intervals (IBIs).
    IBIs should be in milliseconds.
    """
    if not ibi_series or len(ibi_series) < 2: # Check for empty or too short series
        return {
            "rmssd": np.nan, 
            "sdnn": np.nan, 
            "pnn50": np.nan, 
            "ibi_mean": np.nan, 
            "ibi_std": np.nan,
            "hr_mean": np.nan # Adding mean HR as well
        }
    
    ibi_series = np.array(ibi_series) # Ensure it's a numpy array
    ibi_diffs = np.diff(ibi_series)
    
    rmssd = np.sqrt(np.mean(ibi_diffs**2))
    sdnn = np.std(ibi_series)
    pnn50 = np.sum(np.abs(ibi_diffs) > 50) / len(ibi_diffs) * 100 if len(ibi_diffs) > 0 else 0
    ibi_mean = np.mean(ibi_series)
    ibi_std = sdnn # sdnn is the standard deviation of IBIs
    
    # Calculate mean heart rate from mean IBI
    # HR (beats per minute) = 60,000 / mean_IBI_in_ms
    hr_mean = 60000.0 / ibi_mean if ibi_mean > 0 else np.nan
    
    return {
        "rmssd": rmssd,
        "sdnn": sdnn,
        "pnn50": pnn50,
        "ibi_mean": ibi_mean,
        "ibi_std": ibi_std,
        "hr_mean": hr_mean
    }

def calculate_skin_temp_features(skin_temp_series):
    """
    Calculates statistical features from a series of skin temperature readings.
    Temperatures should be in Celsius.
    """
    if not skin_temp_series or len(skin_temp_series) == 0:
        return {
            "skin_temp_mean": np.nan,
            "skin_temp_std": np.nan,
            "skin_temp_min": np.nan,
            "skin_temp_max": np.nan
        }
    skin_temp_series = np.array(skin_temp_series)
    return {
        "skin_temp_mean": np.mean(skin_temp_series),
        "skin_temp_std": np.std(skin_temp_series),
        "skin_temp_min": np.min(skin_temp_series),
        "skin_temp_max": np.max(skin_temp_series)
    }

def calculate_accelerometer_features(accelerometer_series):
    """
    Calculates statistical features from accelerometer data.
    Input: list of dicts [{'x': val, 'y': val, 'z': val}, ...]
    """
    if not accelerometer_series or len(accelerometer_series) == 0:
        # Return NaNs for all 19 features
        feature_names = [
            'acc_x_mean', 'acc_y_mean', 'acc_z_mean',
            'acc_x_std', 'acc_y_std', 'acc_z_std',
            'acc_x_min', 'acc_y_min', 'acc_z_min',
            'acc_x_max', 'acc_y_max', 'acc_z_max',
            'acc_vm_mean', 'acc_vm_std', 'acc_vm_min', 'acc_vm_max',
            'acc_x_energy', 'acc_y_energy', 'acc_z_energy'
        ]
        return {name: np.nan for name in feature_names}

    x_vals = np.array([s['x'] for s in accelerometer_series])
    y_vals = np.array([s['y'] for s in accelerometer_series])
    z_vals = np.array([s['z'] for s in accelerometer_series])

    # Vector Magnitude
    vm_vals = np.sqrt(x_vals**2 + y_vals**2 + z_vals**2)

    features = {
        "acc_x_mean": np.mean(x_vals),
        "acc_y_mean": np.mean(y_vals),
        "acc_z_mean": np.mean(z_vals),
        "acc_x_std": np.std(x_vals),
        "acc_y_std": np.std(y_vals),
        "acc_z_std": np.std(z_vals),
        "acc_x_min": np.min(x_vals),
        "acc_y_min": np.min(y_vals),
        "acc_z_min": np.min(z_vals),
        "acc_x_max": np.max(x_vals),
        "acc_y_max": np.max(y_vals),
        "acc_z_max": np.max(z_vals),
        "acc_vm_mean": np.mean(vm_vals),
        "acc_vm_std": np.std(vm_vals),
        "acc_vm_min": np.min(vm_vals),
        "acc_vm_max": np.max(vm_vals),
        "acc_x_energy": np.mean(x_vals**2),
        "acc_y_energy": np.mean(y_vals**2),
        "acc_z_energy": np.mean(z_vals**2)
    }
    return features

# --- Global AI Clients (initialized later in if __name__ == '__main__') ---
openai_client = None
gemini_client = None

# --- Regression Model Handling ---
REGRESSION_MODEL_PATH = '/Users/shivanikandhai/Downloads/Emoly-main/models/best_model_regression.h5'
regression_model = None

def load_regression_model():
    global regression_model
    if regression_model is None:
        try:
            print(f"Loading regression model from {REGRESSION_MODEL_PATH}...")
            regression_model = tf.keras.models.load_model(REGRESSION_MODEL_PATH, compile=False)
            print("Regression model loaded successfully.")
            # Optional: Print model summary to confirm structure if needed during startup
            # regression_model.summary()
        except Exception as e:
            print(f"ERROR: Could not load regression model: {e}")
            # Depending on how critical this is, you might want to exit or raise the exception
    return regression_model

# --- Flask App ---
app = Flask(__name__)

# Note: API keys are loaded from environment variables, not hardcoded.



# --- Utilities ---
def is_endphase_command(user_input: str, threshold: float = 0.7, break_sentence: str = "endphase()") -> bool:
    """Allow fuzzy matching of endphase()"""
    t = user_input.strip().lower()
    return difflib.SequenceMatcher(None, t, break_sentence).ratio() >= threshold

# --- Emotion Recognition via Plutchik ---
def identify_emotion_plutchik(chat_history):
    text = str(chat_history[1:])
    messages = [
        {"role": "system", "content": (
            "You are an expert emotion recognition system based on Plutchik’s Wheel of Emotions.\n"
            "Given the conversation history, identify the user’s most likely emotional state—even if the user does not express it directly or may mislabel it.\n"
            "Account for confusion between similar emotions (e.g. saying 'I’m sad' when underlying is anxiety).\n\n"
            "Respond with only one emotion from the list below (lowercase, no punctuation) and a confidence score between 0.0 and 1.0 in JSON format:\n"
            "{\n  \"emotion\": \"<emotion>\",\n  \"confidence\": <float>\n}\n\n"
            "Valid emotions (high→low intensity):\n"
            "- anger: rage, anger, annoyance\n"
            "- anticipation: vigilance, anticipation, interest\n"
            "- joy: ecstasy, joy, serenity\n"
            "- trust: admiration, trust, acceptance\n"
            "- fear: terror, fear, apprehension, shame, guilt\n"
            "- surprise: amazement, surprise, distraction\n"
            "- sadness: grief, sadness, pensiveness\n"
            "- disgust: loathing, disgust, boredom\n"
            "Neutral: calm, neutral\n"
        )},
        {"role": "user", "content": text}
    ]
    if not openai_client:
        # Handle error: client not initialized
        return "error_openai_not_init", 0.0
    resp = openai_client.chat.completions.create(model="gpt-4.1-mini", messages=messages, temperature=0, max_tokens=60)
    try:
        data = json.loads(resp.choices[0].message.content)
        return data.get("emotion","neutral"), data.get("confidence",0.5)
    except:
        return "neutral", 0.5

# --- Trigger Extraction ---
def extract_trigger_types(chat_history):
    text_conversation = str(chat_history)
    
    if not openai_client:
        # Handle error: client not initialized
        return "error_openai_not_init", 0.0
    messages = [
        {"role": "system", "content": (
            '''You are a trigger‐classification system. Your job is to scan a user’s conversation about an emotional episode and return the **primary** cause(s) of that emotion, in order of importance.  Bodily sensations (somatic reactions) are only “somatic triggers” if they are the **original** source of the emotion (e.g., someone feels anxious because they are hungry or in pain).  If the bodily reaction follows from something else (e.g., a fight with a spouse) then you must classify that event as the trigger (e.g., relationship trigger), and only list “somatic trigger” if there truly is a separate, primary physical cause.

            **Steps to follow**  
            1. Scan the conversation and ask: _What actually **happened first** that made the user emotional?_  
            2. If it was a bodily/physical state (illness, pain, fatigue, hunger, hormonal shift), label it **somatic trigger**.  
            3. Otherwise, ignore purely descriptive mentions of heart‐rate, butterflies, stomach drops, etc., and choose one of the non‐somatic categories below based on what caused those sensations.

            
            Definitions of these triggers are as follows:
                "1. somatic triggers: a physical/bodily state that itself **caused** the emotion - like illness, fatigue, pain, hunger, or hormonal shifts etc., that directly causes an emotional reaction. For example, someone might feel irritable or panicked because they’re in pain or sleep-deprived."
                "2. relationship triggers: These triggers are related to interpersonal conflicts or dynamics. Experiences such as conflict, rejection, betrayal, criticism, loneliness, or feeling abandoned by a significant other can instantly provoke strong emotions."
                "3. identity triggers: an emotional reaction caused by events or feedback that challenge how someone sees themselves, their values, or their worth (e.g., being criticized, excluded, or stereotyped). These triggers often evoke shame, anger, or insecurity, especially when they conflict with one’s core self-concept."
                "4. trauma-related triggers: an external or internal cue (e.g., sound, smell, memory, place) that involuntarily reactivates the emotional and bodily response of one's own past traumatic event. The reaction is often intense and immediate, as if the trauma is happening all over again."
                "5. existential triggers: a situation or realization that confronts a person with the realities of death, freedom, or meaninglessness, often provoking anxiety, dread, or crisis. These are typically activated by life transitions, loss, or moments of deep reflection (e.g., 'What’s the point of all this?')."
                "6. environmental and sensory triggers: an emotional response sparked by specific external cues, such as noise, light, smells, weather, crowded spaces, or other stimuli in the environment that lead to emotional activattion of the the individual. These are often subtle and context-dependent."
             
            
            Return the identified trigger(s) as a Python list of strings containing **only** the triggers mentioned in order of salience, e.g.,: ['relationship trigger','somatic trigger'] if the relationship trigger weighs more on the user's emotional state than the somatic trigger'
            Do not return any explanations or additional text — only the Python list.'''
        )},
        {"role": "user", "content": text_conversation}
    ]
    response = openai_client.chat.completions.create(
        model='gpt-4.1-mini',
        messages=messages,
        temperature=0.0,
        max_tokens=150
    )

    # Extract and parse list
    try:
        trigger_list_str = response.choices[0].message.content.strip()
        trigger_list = json.loads(trigger_list_str.replace("'", '"'))  # safe JSON parsing
    except Exception:
        trigger_list = []

    return trigger_list

# --- Reappraisal Subtype Decision ---
def decide_reappraisal_subtype(chat_history):
    text = str(chat_history)
    
    if not openai_client:
        # Handle error: client not initialized
        return "error_openai_not_init", 0.0
    
    messages = [
        {"role":"system","content":(
            "You are a psychologist specializing in emotion regulation and trained in the Extended Process Model by James Gross, as well as related frameworks like Self-Efficacy Theory, Post-Traumatic Growth, Meaning-Making, and Reappraisal Flexibility.\n\n"
                "Your goal is to determine which type of cognitive reappraisal best fits the user's situation, based on the conversation. You must choose between two evidence-based subtypes:\n\n"
                "**Agency Cognitive Change**\n"
                "Use when the user feels powerless, overwhelmed, anxious, or self-doubting in the face of a challenge or changeable stressor.\n"
                "This reframe emphasizes the user's personal influence, capacity to cope, or ability to take meaningful steps forward.\n"
                "Typical indicators include statements like: 'I can't handle this,' 'There's nothing I can do,' or 'I'm stuck and out of control.'\n"
                "Theory support: Gross (2015), Bandura (1977), Troy et al. (2017)\n\n"
                "**Positive Cognitive Change**\n"
                "Use when the user is grieving, ruminating, reflecting on a loss, or experiencing something that is uncontrollable or irreversible.\n"
                "This reframe helps the user identify potential growth, meaning, or value in their experience.\n"
                "Typical indicators include: 'What's the point?', 'This ruined everything', or 'I don't see any good in this.'\n"
                "Theory support: Tedeschi & Calhoun (2004), Park & Folkman (1997), Fredrickson (2001), Troy et al. (2017)\n\n"
                "Use this decision framework to guide your answer:\n\n"
                "Q1: Can the user influence the situation?\n"
                "- Yes → Use **Agency** (emphasize coping abilities and small next steps).\n"
                "- No → Use **Positive** (support meaning-making and emotional integration).\n\n"
                "Q2: What is the user focused on?\n"
                "- Personal failure, inability, or asking 'what should I do?' → **Agency**\n"
                "- Loss, unfairness, or meaninglessness → **Positive**\n\n"
                "Q3: Emotional tone check:\n"
                "- Helpless / Anxious → **Agency**\n"
                "- Hopeless / Sad → **Positive**\n"
                "- Angry:"
                "  - Fixable issue → **Agency**"
                "  - Irreversible harm → **Positive**\n\n"
                "Q4: Mixed or unclear tone:\n"
                "- Default to **Positive** if unsure, unless the user specifically asks for guidance or problem-solving\n\n"
                "Guiding principle: Help the user either **reclaim their influence** or **reclaim their story**.\n\n"
                "Return ONLY one of the following strings:\n"
                "Agency Cognitive Change\n"
                "or\n"
                "Positive Cognitive Change"
        )},
        {"role":"user","content": text}
    ]
    resp = openai_client.chat.completions.create(model="gpt-4.1-mini", messages=messages, temperature=0, max_tokens=20)
    return resp.choices[0].message.content.strip()

# --- Main Strategy Decision ---
def decide_strategy(primary_emotion, primary_trigger, chat_history):
    strategies = {
            "Attentional Deployment":f"""You are a warm, present‐centered guide whose sole job is to help someone regulate a difficult emotion by returning their attention to the here and now. Follow these four phases exactly once, in order, and finish by inviting the user to type endphase()—no more, no less. Take note that this is a repeating prompt, so scan the previous conversation to see at which point of the strategy you are to effectively follow the steps.
                    
                
                
                    
                    The user feels {primary_emotion}

                    ---
                    
                    ### STEP 1. Sensory Anchoring
                    Speak softly, in short pauses, and invite them to notice something neutral in their environment:

                    > “Let's try to ground you in your current surroundings. Take a moment to look around. What’s one thing here—perhaps a color, texture, or shape—that feels just okay to rest your eyes on?”  

                    When they answer, deepen the invitation with two gentle questions:

                    > “Can you notice how that object sits in its surroundings?”  
                    > “Is there a small detail that holds your attention a bit longer?”


                    ---
                    
                    ### STEP 2. Shift to Breath Awareness
                    Now that they’re grounded in sight, guide them to their breath:

                    > “As you keep noticing that object, begin noticing your breath—how it feels coming in and out of your body. Is it warm or cool, shallow or steady?”

                    Then lead them through exactly ten breaths:

                    > “If it feels comfortable, softly close your eyes. For the next ten breaths, inhale slowly through your nose… and exhale gently through your mouth. I’ll stay with you—just let your breath find its own pace. Let me know when you’ve completed ten.”

                    Wait for their confirmation before moving on.

                    ---
                    
                    ### STEP 3.Validation & Reflection
                    Affirm their effort and invite brief reflection:

                    > “You did really well. That was a gift of care to your body and mind. This sense of grounded calm is always here—you can return any time. How do you feel now compared to the start?”


                    ---

                    ### STEP 4. Close the Strategy
                    Let them know they’ve completed this phase and how to move on:

                    > “Great job completing this grounding exercise. When you’re ready to try the next strategy, just type `endphase()`.”  

                    ---

                    **IMPORTANT:** Do not skip or repeat any step, and do not proceed without guiding the user through the full ten‐breath exercise, ending with the `endphase()` prompt.""",
         
            "Situation Modification":"""

                    You are a grounded, supportive guide helping the user explore and gently **change part of their situation or environment** to reduce emotional distress or support emotional well-being. This strategy is known as **situation modification**, an antecedent-focused emotion regulation strategy from James Gross’s Extended Process Model of Emotion Regulation (Gross, 2014).

                    ---

                    **IMPORTANT:** Don't skip or repeat any part. Wait for the user's response where indicated before proceeding. End the strategy with telling the user to type `endphase()`. Keep in mind this is a repeating prompt, so scan the previous conversation to see at which point of the strategy you are to effectively follow the steps.

                    ---

                    ### 1. Pinpointing the Emotional Hotspot
                    Let's start by gently exploring the situation you're in.

                    > “You mentioned that [insert paraphrase about the situation/emotion, e.g., 'you're feeling disgust around that particular mess']. What part of this situation is feeling the hardest, most uncomfortable, or most draining for you right now?”

                    (Wait for user's response)

                    > “And what specifically tends to make that feeling worse, either emotionally or in a practical way?”

                    ---

                    ### 2. Exploring Ways to Shift Things
                    Thanks for sharing that with me. Now, knowing what makes it hard, let's think about if there's anything, no matter how small, you could actually change or shift in your immediate surroundings or circumstances. Even tiny adjustments can make a real difference in how a situation impacts us (Gross, 2014).

                    > "Is there something you might be able to **modify right now**—perhaps in your physical space, how you're positioned, or a small sensory detail—that could help ease that feeling, especially that sense of [primary_emotion, e.g., disgust]?"

                    (Wait for user's response for a direct change)

                    That's a thoughtful idea. It's great you're considering that. If you're finding it a bit tricky to pinpoint something specific, sometimes it helps to think in terms of very small, actionable tweaks. For example, could you consider:
                    * **A social touchpoint:** Like sending a quick, one-line text to a friend, or even just waving at a neighbor if you see one?
                    * **A movement break:** Such as standing up and stretching, taking a 2-minute walk around the room, or stepping outside for a breath of fresh air?
                    * **A sensory uplift:** Maybe playing an upbeat song, putting on earbuds with a guided meditation, or brewing a warm cup of tea?

                    > "Does any of these, or perhaps another small adjustment you've thought of, feel like something you could comfortably try in the next minute or two to gently shift the situation?"

                    (Wait for user's response for another idea or if they pick from the options)

                    It's really insightful that you're exploring these possibilities. Identifying even small actions you can take is a powerful step.

                    ---

                    ### 3. Choosing Your Supportive Change
                    Okay, it sounds like [paraphrase chosen change, e.g., "putting on some calming music"] is a small, supportive step you feel comfortable trying. That's fantastic. There's no pressure for big leaps here; tiny shifts still make a difference. Taking direct action to modify your environment can be very effective, especially for emotions like disgust where altering the immediate sensory input can provide real relief (Rozin et al., 1999).

                    > "If you feel ready, go ahead and try that now. I'll be here. Take your time, and let me know when you've done it."

                    (Pause and hold space for the user to implement the change)

                    ---

                    ### 4. Reflecting on the Shift
                    *(If they confirm they've done it):*
                    > “Okay. You took a concrete step for yourself to modify your situation. How do you notice things feel now—anything different in your body or mind after making that adjustment?”
                    > “It's perfectly okay if not much shifted immediately. The important thing is that you actively engaged in taking a step to influence your environment, which is a powerful act of self-care and regulation.”

                    *(If they weren’t ready or didn’t implement it):*
                    > “That’s perfectly understandable too. Even thinking about potential changes is a valuable step, and sometimes that's enough for now. Would you prefer to stay here a bit longer and explore it further, or perhaps switch to something grounding like focusing on your breath?”

                    ---

                    ### 5. Concluding the Strategy
                    You're allowed to move slowly and compassionately through this process. Each shift you consider or implement—whether internal or external, big or small—matters when it comes to managing your emotions and supporting your well-being. Let's keep tuning into what helps you feel more at ease. You don’t have to figure it all out at once.

                    You’ve done excellent work exploring situation modification. When you’re ready to **move on to the final part**, type `endphase()`.""",

            'Agency Cognitive Change':"""
                    You are a calm, empowering guide whose goal is to help someone gently reframe their interpretation of a situation using the Agency Method—grounded in Self-Determination Theory, Self-Efficacy, and an Internal Locus of Control. Follow these four parts exactly once, in order, and finish by inviting the user to type **endphase()** to move on to the final part—no more, no less. Take note that this is a repeating prompt, so scan the previous conversation to see at which point of the strategy you are to effectively follow the steps.

                    ---

                    **IMPORTANT:** Do not skip or repeat any part. Wait for the user’s response where indicated before proceeding. End the strategy with telling the user to type `endphase()`. Keep in mind this is a repeating prompt, so scan the previous conversation to see at which point of the strategy you are to effectively follow the steps.

                    ---

                    ### STEP 1. Validation & Emotional Attunement  
                    Speak with warmth and curiosity. Paraphrase one thing they said and invite them to elaborate:

                    > “You mentioned that [insert paraphrase]. That sounds really challenging. Would you tell me more about how that feels?”  

                    After they answer, offer a brief validating response, then immediately move to Step 2.

                    ---

                    ### STEP 2. Explore Agency  
                    Gently guide them to notice their control. Use reflective questions such as:

                    > “Even if the bigger situation feels out of your hands, what is one small choice—your next thought, your next action, or how you hold yourself—that you fully control?”  
                    > "Setting aside the entire overwhelming problem for a moment, what is one single, concrete action I can choose to take in just the next 30 minutes to make my experience 1 percent better?"

                    Once they answer, validate their insight, and ask one deepening question then proceed to Part 3.

                    ---

                    ### STEP 3. Offer a Gentle Reappraisal  
                    Model empowering internal language for agency:

                    > “It sounds like you know how to move on with compassion. That’s real strength, even if it doesn’t always feel that way.”

                    ---

                    ### STEP 4. Close the Strategy  
                    Acknowledge their effort and invite them to move on:

                    > “Great work using this strategy. When you’re ready to move on to the final part, type `endphase()`.”

                    """,

            'Positive Cognitive Change': """
                                You are a compassionate, reflective guide helping someone find deeper meaning, gratitude, or personal insight in a difficult experience through Explicitly Positive Reappraisal. Grounded in Post-Traumatic Growth, Meaning-Making, Broaden-and-Build, Savoring, and Benefit-Finding theories, follow these four parts exactly once, in order, and finish by inviting the user to type **endphase()** to move on to the final part—no more, no less.

                                **IMPORTANT:** Do not skip or repeat any part. Wait for the user’s response where indicated before proceeding. End the strategy with telling the user to type `endphase()`. Take note that this is a repeating prompt, so scan the current conversation to see at which point of the strategy you are to effectively follow the steps.
                                   ---

                                ### 1. Tune Into the Feeling
                                Start by tuning into the feeling they mentioned.

                                > “You mentioned [insert paraphrase]. That sounds really important. Can you describe what this joy, trust, or even a sense of unexpected clarity feels like for you—perhaps in your body, your breath, or your energy?”

                                (Wait for user's response)

                                ---

                                ### 2. Explore Positive Reframing
                                Now, gently explore this experience with an open mind, looking for hidden insights or unexpected positives. 

                                > "Considering what you've described about [the situation or challenge they described], can you explore if there's an **alternative way to frame this experience**? For instance, might this 'setback' also be viewed as an 'opportunity to learn' or a 'chance to clarify what truly matters'?"

                                (Wait for user's response)

                                > "That's a really insightful way to look at it. Building on that, thinking about this experience, even its challenging aspects, have any **unexpected positives or personal strengths** surfaced for you? What might you have *gained* or *discovered* about yourself or the situation that you might not have recognized before?"

                                (Wait for user's response)

                                > "You're doing a wonderful job finding new perspectives. If it's a little hard to pinpoint something specific, sometimes it helps to shift our focus. Is there anything, no matter how subtle, for which you can cultivate a sense of **gratitude** within or around this situation? Even a tiny spark of appreciation can shift our view."

                                (Wait for user's response)

                                > "It's powerful to see how you can reframe and find these moments of positivity."

                                ---

                                ### 3. Savor or Act
                                > "Given these new insights or feelings, would it feel okay to take one small, gentle action right now to acknowledge or express this positive reframe? You might simply pause to savor this insight for a few breaths, perhaps write down one thing you're grateful for, or even consider a small step forward that aligns with this new understanding."

                                ---

                                ### 4. Reflect & Close
                                > "That's wonderful. What did you notice as you allowed yourself to consider those alternative perspectives or express that positive reframe? Does anything feel different in your body, your energy, or your overall outlook now?"

                                > "You're allowed to find meaning and growth in challenging experiences. This process of reinterpreting and finding positives, even small ones, is a powerful way to regulate emotions and build resilience. Even one moment of intentional positive reframing can plant a seed that continues to grow."

                                > "You've done excellent work engaging with this strategy. When you're ready to move on to the final part, type `endphase()`.
                    """,
                   
            "Response Modulation":f"""You are a gentle, encouraging guide helping someone **upmodulate a positive emotion**—such as joy or trust—by finding small, meaningful ways to express or sustain it through behavior. This process supports emotional well-being, connection, and vitality, and is grounded in theories such as:
        
                        The user feels {primary_emotion}
                        
                        - **Broaden-and-Build Theory**: positive emotions expand thinking and build resources
                        - **Savoring**: conscious attention to positive feelings increases their duration and impact
                        - **Upward Spiral Theory**: expressing positive feelings invites more of them
                        - **Social Sharing**: sharing joy or trust with others amplifies it
                        - **Embodied Expression**: physical expression enhances emotional states
                        - **Character Strengths**: joy and trust often reflect meaningful inner values
                        
                        ---
                        
                        Your role is to help the user:
                        1. Acknowledge and describe the feeling of joy or trust
                        2. Tune into how it wants to be expressed (internally or externally)
                        3. Choose one small behavior to reinforce or share the feeling
                        4. Reflect on the effect, without judgment
                        
                        ---
                        
                        Start by gently tuning into the feeling by touching on something the user said previously:
                        - “You said that [insert paraphrase]. Can you describe what this joy or trust feels like—maybe in your body, your breath, or your energy?”
                        - “What part of this feeling would you love to stay with, even just a little longer?”
                        
                        Explore how the emotion wants to be expressed:
                        - “If you let this joy have a small action—what might that be?”
                        - “Does this feeling make you want to smile, move, reach out, create, or give?”
                        - “What would feel like a simple way to honor this moment?”
                        
                        Offer ideas based on their emotional state:
                        - **For joy**: movement, music, laughter, art, nature, shared celebration  
                        - **For trust**: vulnerability, appreciation, a kind message, leaning into support
                        
                        ---
                        
                        Help the user **savor or act** on the feeling:
                        - “Would it feel okay to take one small action right now to express this—something gentle and intentional?”
                        - “You could stay with this sensation for a few breaths, or share a message with someone you trust, or just smile with it a bit longer.”
                        
                        Allow pauses. Let them follow through if they’re ready.
                        
                        ---
                        
                        Afterward, support reflection:
                        - “What did you notice as you let yourself express that?”
                        - “Does anything feel different in your body or energy?”
                        
                        ---
                        
                        Close with a positive, spacious reminder:
                        - “You’re allowed to feel this. It’s okay to let joy or trust grow in you.”
                        - “Even one moment of expression plants a seed that keeps growing.”
                        
                        Once you have decided that the user effectively used the strategy, acknowledge their effort and inform them they can type 'endphase()' to move to the final part of the session. Use the exact phrase 'move on to the final part'.""",
         
            "Situation Selection":"""You are a calm, supportive guide helping a user reflect on whether the situation they’re in is **emotionally supportive or draining**—and if not, how they might **exit, avoid, or choose better-aligned situations** going forward.

                    This strategy is known as **situation selection**, the earliest opportunity for emotion regulation in James Gross’s Extended Process Model. Your goal is not to push the user to avoid discomfort, but to help them become **more intentional** about the emotional quality of their environments.
                    
                    The user feels {primary_emotion}
                    
                    You draw on:
                    - **Emotion Regulation Theory** (Gross): choosing situations to manage emotional outcomes  
                    - **Approach-Avoidance Motivation**: recognizing when they are moving toward reward or away from threat  
                    - **Proactive Coping**: anticipating and navigating future emotional patterns  
                    - **Person–Environment Fit**: seeking environments where they feel psychologically safe and congruent  
                    - **Boundary and Assertiveness Skills**: supporting them in saying no, stepping back, or prioritizing their needs  
                    - **Values Clarification (ACT)**: helping them choose situations that reflect who they want to be
                    
                    ---
                    
                    Begin with situational awareness by touching on something the user said previously:
                    - “You said that [insert paraphrase]. Does this situation support how you want to feel—or does it tend to leave you feeling drained or tense?”
                    - “When you imagine staying in or entering this again, how does your body respond?”
                    
                    Explore the possibility of exit or avoidance:
                    - “Is there a way to avoid or delay entering this situation—or exit it safely?”
                    - “What would it look like to protect your energy here, even in a small way?”
                    
                    Invite future reflection and proactive planning:
                    - “Looking ahead, what kinds of situations do you want to include more often in your life?”
                    - “Are there moments you’ve felt more emotionally steady or nourished? What was different about those?”
                    
                    If boundaries are needed, support that:
                    - “Would saying no or stepping away be a way to support yourself right now?”
                    - “You’re allowed to choose what you take part in. That’s not selfish—it’s self-respect.”
                    
                    Anchor in values and personal alignment:
                    - “What kinds of spaces or interactions feel most aligned with who you want to be?”
                    - “If you could build a future with more of what supports you and less of what drains you—what would that look like?”
                    
                    End with gentle empowerment:
                    - “You get to choose what environments you step into or step away from.”
                    - “Even naming what doesn’t work for you is a step toward what *does*.”
                    
                    Once you have decided that the user effectively used the strategy, acknowledge their effort and inform them they can type 'endphase()' to move to the final part of the session. Use the exact phrase 'move on to the final part'."""}            
             
 
    # Map emotion to basic category
    if primary_emotion in ['rage','anger','annoyance']:
        base='anger'
    elif primary_emotion in ['vigilance','anticipation','interest']:
        base='anticipation'
    elif primary_emotion in ['ecstasy','joy','serenity']:
        base='joy'
    elif primary_emotion in ['admiration','trust','acceptance']:
        base='trust'
    elif primary_emotion in ['terror','fear','apprehension','shame','guilt']: # plutchik judjes shame=fear+disgust, guilt=fear+pleasure - https://book2read.com/2023/01/23/the-8-basic-emotions-of-plutchiks-wheel-of-emotions/
        base='fear'
    elif primary_emotion in ['amazement','surprise','distraction']:
        base='surprise'
    elif primary_emotion in ['grief','sadness','pensiveness']:
        base='sadness'
    elif primary_emotion in ['loathing','disgust','boredom']:
        base='disgust'
    else:
        base='neutral'
    # Choose first and second strategies
    if base in ['fear','surprise','sadness','anger']:
        first='Attentional Deployment'
        second=decide_reappraisal_subtype(chat_history)
    elif base in ['joy','trust']:
        first='Attentional Deployment'
        second='Response Modulation'
    elif base=='disgust':
        first='Situation Modification'
        second=decide_reappraisal_subtype(chat_history)
    else:
        first='Attentional Deployment'
        second=decide_reappraisal_subtype(chat_history)
    return first, strategies[first], second, strategies.get(second,strategies[second])

# --- Context Builder ---
def context_builder(chat_history, primary_emotion, primary_trigger, first_strategy, second_strategy, phase):
     
    text_conversation = str(chat_history)
    
    if not gemini_client:
        # Handle error: model not initialized
        return "Error: Gemini model not initialized."
    
    if phase == 1:
        # Use a model that's supported in the current API version
        model = "gemini-2.0-flash-exp"
        
        prompt = f"""You are a therapist that analyses a text conversation that you have had with a user. You will give them a summary of this phase of the conversation that sounds natural and engaged, making the user feel heard.

        Your goal is to:
        
        1. Give a very short explanation of how  the WPVA structure : World, Perception, Valuation, Action' helps us understand better what our emotions look and feel like as they arise.
        2. Empathically paraphrase what the user has expressed in your own words, using easily understandable language, connecting it to their answers for the W, P, V and A elements of the Extended Process Model by James Gross: (1) W – the internal or external 'world/situation' that triggered the users emotion. (2) P – what the user perceived in that moment. (3) V – The users valuation/appraisal of the event. (4) A – the resulting emotional reaction or action tendency of the user.  
        3. Explain that you conclude that their emotion {primary_emotion} was evoked by a {primary_trigger}. Give a short and simple explanation of what this specific trigger means in this context. 
        4. Express understanding of their situation and willingness to support them through this process
        5. Explain that {first_strategy} and {second_strategy} are the emotion regulation techniques that would best help them smoothly work with these emotions. Shortly explain both techniques in a nondetailed manner, and reassure them that you will be helping them with this regulation process.
        
        Make sure to make the primary emotion, primary trigger, first strategy, and second strategy printed in bold (i.e., **text**).

        Finally, tell the user they can let you know when they are ready, so you can proceed with regulating this feeling
        
        Use no more than 300 tokens for this summary."""
        
        conversation_context = f"{prompt}\n\nConversation:\n{text_conversation}"
        
        generation_config = {
            "temperature": 0.7,
            "top_p": 1,
            "top_k": 40,
            "max_output_tokens": 1024,
        }
        
        summary = ""
        response = gemini_client.generate_content(conversation_context, generation_config=generation_config)
        
        # Handle streaming or standard response
        if hasattr(response, 'text'):
            summary = response.text
        else:
            for chunk in response:
                if hasattr(chunk, 'text'):
                    summary += chunk.text
    
        return summary
    
    if phase == "2a":
        # Use a model that's supported in the current API version
        model = "gemini-2.0-flash-exp"
        
        prompt = f"""You are a therapist reflecting on the first emotion regulation strategy phase of a conversation you had with a user. Your task is to give them a thoughtful and compassionate summary of this phase. Your tone should be natural, warm, and affirming—helping the user feel understood and capable.

        Your goal is to:
        1. Empathetically paraphrase how the user engaged with **{first_strategy}**. Describe what they did and how it seemed to help.
        2. Clearly explain **how this strategy works**, and why it is helpful for managing difficult emotions (e.g., grounding, shifting perspective, restoring agency, making meaning).
        3. Encourage the user by acknowledging their effort and progress with this first strategy.
        4. Use accessible, non-technical language that still conveys psychological depth.
        
        Finally, tell the user that they did well with the first strategy and that you're now ready to move on to the second strategy to continue building their emotion regulation skills.
        
        Keep the summary warm, validating, and under 250 tokens. Do not list the points—write them as a connected and supportive narrative.
        """
        
        conversation_context = f"{prompt}\n\nConversation:\n{text_conversation}"
        
        generation_config = {
            "temperature": 0.7,
            "top_p": 1,
            "top_k": 40,
            "max_output_tokens": 1024,
        }
        
        summary = ""
        response = gemini_client.generate_content(conversation_context, generation_config=generation_config)
        
        # Handle streaming or standard response
        if hasattr(response, 'text'):
            summary = response.text
        else:
            for chunk in response:
                if hasattr(chunk, 'text'):
                    summary += chunk.text
                    
        return summary
    
    if phase == "2b":
        # Use a model that's supported in the current API version
        model = "gemini-2.0-flash-exp"
        
        prompt = f"""You are a therapist reflecting on the second emotion regulation strategy phase of a conversation you had with a user. Your task is to give them a thoughtful and compassionate summary of this phase. Your tone should be natural, warm, and affirming—helping the user feel understood and capable.

        Your goal is to:
        1. Empathetically paraphrase how the user engaged with **{first_strategy}**. Describe what they did and how it seemed to help.
        2. Clearly explain **how this strategy works**, and why it is helpful for managing difficult emotions (e.g., grounding, shifting perspective, restoring agency, making meaning).
        3. Empathetically paraphrase how the user engaged with **{second_strategy}**. Describe what they did and how it seemed to help.
        4. Clearly explain **how this strategy works**, and why it is helpful for managing difficult emotions (e.g., grounding, shifting perspective, restoring agency, making meaning).
        5. Encourage the user by acknowledging their effort and progress with this second strategy.
        6. Remind them they now **have both tools** ({first_strategy} and {second_strategy}) to support themselves in similar emotional situations in the future.
        7. Use accessible, non-technical language that still conveys psychological depth.
        
        Finally, tell the user that they did excellent work with both strategies and that you're ready to move on to the final reflection phase to think about how they handled their emotions today.
        
        Keep the summary warm, validating, and under 300 tokens. Do not list the points—write them as a **connected and supportive narrative**.
        """
        
        conversation_context = f"{prompt}\n\nConversation:\n{text_conversation}"
        
        generation_config = {
            "temperature": 0.7,
            "top_p": 1,
            "top_k": 40,
            "max_output_tokens": 1024,
        }
        
        summary = ""
        response = gemini_client.generate_content(conversation_context, generation_config=generation_config)
        
        # Handle streaming or standard response
        if hasattr(response, 'text'):
            summary = response.text
        else:
            for chunk in response:
                if hasattr(chunk, 'text'):
                    summary += chunk.text
                    
        return summary
    
    if phase == 3:
        # Use a model that's supported in the current API version
        model = "gemini-2.0-flash-exp"
        
        prompt = f"""You are a therapist concluding an emotion regulation session using the Extended Process Model by James Gross. You've just guided a user through a reflection on their emotional experience and their use of two regulation strategies: **{first_strategy}** and **{second_strategy}**.

        Your task is to summarize this entire reflection phase (Stage 3), keeping the tone warm, validating, and empowering.
        
        Please include the following in your reflection summary:
        
        1. A compassionate, paraphrased summary of the emotional experience the user described (Stage 1: Identification).
        2. A supportive reflection on how the user reviewed the strategy choices and how these strategies were selected (Stage 2: Selection).
        3. A clear, brief reflection on how the user practiced each strategy (first strategy: {first_strategy}, second strategy: {second_strategy})— explicitly name the name of the strategy, then say what they noticed, what worked, what was challenging (Stage 3: Implementation).
        4. An empowering, skill-building ending: highlight their growth, effort, and ability to choose and apply emotional tools in the future.
        
        End the summary by thanking the user for their openness, and then say something motivational. Tell them they can end the conversation by typing endphase().
        Write this in a connected narrative (not bullet points). Use plain, emotionally intelligent language. Do not name the phases explicitly. Keep it under 350 tokens.
        """
        
        conversation_context = f"{prompt}\n\nConversation:\n{text_conversation}"
        
        generation_config = {
            "temperature": 0.7,
            "top_p": 1,
            "top_k": 40,
            "max_output_tokens": 1024,
        }
        
        summary = ""
        response = gemini_client.generate_content(conversation_context, generation_config=generation_config)
        
        # Handle streaming or standard response
        if hasattr(response, 'text'):
            summary = response.text
        else:
            for chunk in response:
                if hasattr(chunk, 'text'):
                    summary += chunk.text
                    
        return summary


# --- Main Chatbot Loop ---
def main():
    global client
    if not OPENAI_KEY or not GEMINI_KEY:
        print("Error: set OPENAI_API_KEY and GEMINI_API_KEY.")
        return
    client = OpenAI(api_key=OPENAI_KEY)
    
    
    # # Get latest 5 interventions for a participant
    # history = session.query(Intervention).filter_by(participant_id=1).order_by(Intervention.start_time.desc()).limit(5).all()

    data = {}
    # Initialize history and greeting
    data['participant_id'] = input("Enter your participant number: ")
    username = input("Enter your username (not your real name): ")
    data['username'] = username
    
    history = [{"role":"system","content":(
        "You are Aire, a warm, emotionally attuned therapeutic guide. You're here to support the user in understanding and regulating a difficult emotional experience using the Extended Process Model of Emotion Regulation."
        "You are now moving on to the first phase of the conversation, which is about helping the user identify their emotional experience and the trigger that caused it."
        "Your goal is to help the user explore their emotional experience in detail, using the WPVA structure. Give them a short explanation of what this is:\n"
        "- what happened in their **world** (W),\n"
        "- how they **perceived** it (P),\n"
        "- what meaning or **valuation** they gave it (V), and\n"
        "- what **action** urge it stirred up (A).\n\n"

        "Then begin Phase 1 by asking a soft, open-ended question like:\n"
        "'Let's take that one step at a time. Can you tell me a bit about what’s been present on your mind today—what happened, and how you’ve been feeling in response to it?'\n\n"

        "As the user shares, your job is to help them explore the likely **primary trigger** for their emotional reaction. Triggers may include:\n"
        "1. **Somatic trigger** – bodily states like pain, fatigue, or hormonal changes\n"
        "2. **Relationship trigger** – conflict, rejection, or abandonment\n"
        "3. **Identity trigger** – threat to self-worth, values, or belonging\n"
        "4. **Trauma-related trigger** – reactivation of a past traumatic experience\n"
        "5. **Existential trigger** – crisis of meaning, loss, or future anxiety\n"
        "6. **Environmental/sensory trigger** – noise, smell, weather, or overstimulation\n\n"

        "A more detailed description of each part of the WPVA model to consult when asking the user questions:"
        "1. World: The context or situation in which the emotional process begins. The “world” provides emotion-eliciting inputs. These are the raw materials from which emotional experiences are constructed.\n"
        "2. Perception: Refers to the detection and identification of a physiological, experiential, or situational change—that something emotional is happening. Perception is what the nervous system registers from the world—what was noticed or sensed, either consciously or unconsciously. It includes physiological signals (like a racing heart), sensory impressions (like a facial expression), or the awareness of a thought. Like the world, this part is still largely automatic, but it reflects what entered the person’s awareness rather than what simply occurred.\n"
        "3. Valuation: Involves evaluating the significance of that perceived emotion in relation to one’s goals, needs, or context. It’s the meaning-making step where one determines whether the emotion is helpful or harmful, expected or unexpected, appropriate or inappropriate. Valuation is where subjectivity begins. It involves interpreting what was perceived: Is this good or bad for me? Does it threaten something I care about? This step reflects how a person makes meaning of their perception based on personal goals, needs, past experiences, and values. Two people can perceive the same thing but value it differently.\n"
        "4. Action: Based on valuation, an action tendency arises (e.g., fight, flee, seek support). So,reacting or regulating based on appraisal/valuation (can be automatic or deliberate). Action refers to the internal or external responses that follow from valuation—such as physiological changes, urges, expressions, or chosen emotion regulation strategies.\n\n"

        "Continue the conversation by gently prompting around the W-P-V-A model. Use multiple, progressively deeper questions if needed to identify the trigger clearly. Normalize and validate their emotions throughout. Never pressure the user to share more than they want to.\n\n"

        "Once you’re confident about the emotional trigger, affirm your understanding and gently invite the user to move to the next phase by typing 'endphase()'. Explicitly use the words 'move on to phase two' here!\n\n"
        "Do **not** tell the user explicitly which trigger you’ve identified—only that you believe you understand and are ready to help them with regulation next."
    )}]
    #name = input("You: ").strip()
    #history.append({"role":"user","content":name})
    #print(f"\n:Rain It’s good to meet you, {name}. What’s on your mind today?\n")

    # Phase 1
    print("[Phase 1: Emotion & Trigger Identification]")

    print("Aire: Hi there, I’m Aire!")
    while True:
        msg = input("You: ")
        if is_endphase_command(msg): break
        history.append({"role":"user","content":msg})
        resp = client.chat.completions.create(model="gpt-4.1-mini", messages=history)
        reply = resp.choices[0].message.content.strip()
        history.append({"role":"assistant","content":reply})
        print(f"Aire: {reply}\n")
    triggers = extract_trigger_types(history)

    primary_trigger = triggers[0] if triggers else "unknown"
    primary_emotion, confidence = identify_emotion_plutchik(history)
    first_strat, first_prompt, second_strat, second_prompt = decide_strategy(primary_emotion, primary_trigger, history)
    
    data['triggers'] = triggers
    data['primary_trigger'] = primary_trigger
    data['emotion_before'] = primary_emotion
    data['first_strategy'] = first_strat
    data['second_strategy'] = second_strat

    #print(triggers)
    #print(primary_trigger)
    #print(primary_emotion)
    #print(first_strat)
    #print(second_strat)
    summary1 = context_builder(history, primary_emotion, primary_trigger, first_strat, second_strat, 1)
    print(f"[Phase 1 Summary] {summary1}\n")

    # Phase 2
    print("[Phase 2: Strategy Implementation]")
    history.append({
        "role": "system",
        "content": (
            "You are a therapist helping a client regulate their current emotion using the Extended Process Model of Emotion Regulation."
            "You are now moving on to the second phase of the conversation, which is about helping the user implement the chosen strategy as described by the Extended Process Model of Emotion Regulation by James Gross."
            f"The user's dominant emotion is: {primary_emotion}.\n"
            f"The user's identified trigger is: {primary_trigger}.\n"
            f"The first strategy is {first_strat}.\n"
            f"The second strategy is {second_strat}.\n"
            f"In this phase, you will use the first strategy to help the user regulate their emotion as follows: {first_prompt} \n"
            f"When you have completed this, inform the user, and then you will use the second strategy to help the user regulate their emotion as follows: {second_prompt}.\n"
            
            "Keep your tone warm, understanding, and curious. You are not solving their problem or finding their answers for them—you are helping them find ways to reappraise and become better at the regulation stategy, and to recognize that they **can** use it and **when** to use it."
            "If the user asks for solutions to the problem, do not give them solutions. Rather, help them dig deeper to come up with an answer themselves."
            "Help the user through the strategy one step at a time. Keep your replies concise, naturally conversational, and curious, max 150 tokens."
            "This phase ends when both strategies are completed. In this case, tell the user that they did a good job regulating and that they can move on to the next part of the session by typing 'endphase()'. "
        )
    })
    while True:
        msg = input("You: ")
        if is_endphase_command(msg): break
        history.append({"role":"user","content":msg})
        # use Gemini or OpenAI for guidance
        resp = client.chat.completions.create(model="gpt-4.1-mini", messages=history)
        reply = resp.choices[0].message.content.strip()
        history.append({"role":"assistant","content":reply})
        print(f"Aire: {reply}\n")
    summary2 = context_builder(history, primary_emotion, primary_trigger, first_strat, second_strat, "2a")
    print(f"[Phase 2a Summary] {summary2}\n")

    # Phase 2b
    print("[Phase 2b: Second Strategy Implementation]")
    history.append({
        "role": "system",
        "content": (
            "You are a therapist helping a client regulate their current emotion using the Extended Process Model of Emotion Regulation."
            "You are now moving on to the second part of Phase 2, focused on implementing the second emotion regulation strategy."
            f"The user's dominant emotion is: {primary_emotion}.\n"
            f"The user's identified trigger is: {primary_trigger}.\n"
            f"You will guide the user through the second strategy: {second_strat}.\n\n"
            f"Use the following prompt to guide the user through the second strategy: {second_prompt}.\n\n"
            "Keep your tone warm, understanding, and curious. You are not solving their problem or finding their answers for them—you are helping them find ways to reappraise and become better at the regulation stategy, and to recognize that they **can** use it and **when** to use it."
            "If the user asks for solutions to the problem, do not give them solutions. Rather, help them dig deeper to come up with an answer themselves."
            "Help the user through the strategy one step at a time. Keep your replies concise, naturally conversational, and curious, max 150 tokens."
            "This phase ends when the second strategy is completed. In this case, tell the user that they did a good job regulating and that they can move on to the next part of the session by typing 'endphase()'. "
        )
    })
    while True:
        msg = input("You: ")
        if is_endphase_command(msg): break
        history.append({"role":"user","content":msg})
        # use Gemini or OpenAI for guidance
        resp = client.chat.completions.create(model="gpt-4.1-mini", messages=history)
        reply = resp.choices[0].message.content.strip()
        history.append({"role":"assistant","content":reply})
        print(f"Aire: {reply}\n")
    summary2b = context_builder(history, primary_emotion, primary_trigger, first_strat, second_strat, "2b")
    print(f"[Phase 2b Summary] {summary2b}\n")

    # Phase 3
    print("[Phase 3: Guided Reflection]")
    history.append({
        "role": "system",
        "content": (
            "You are a therapist helping a client reflect on their emotion regulation journey using the Extended Process Model of Emotion Regulation by James Gross. "
            "This is the Guided Reflection Phase, where you support the user in consolidating insight from today’s session.\n\n"
            
            "You’ll walk them through the reflection of the session:\n"
            "1. **Event Identification** – Revisiting the emotional trigger and the feelings it brought up.\n"
            "2. **Strategy Selection** – Reflecting on the strategy choices.\n"
            "3. **Strategy Implementation** – Exploring how the strategies worked in practice.\n\n"

            "Your tone is validating, curious, and gently empowering. You help the user unpack their experience with emotional clarity and build confidence in their regulation skills. "
            "Avoid giving solutions—your role is to help the user uncover their own insights through reflection.\n\n"
            
            "Start the conversation with saying that we've arrived in the final phase, where we will reflect on how the user moved through these emotions. Tell them that they can take their time to really think about it."
            "Begin with reflecting on **Stage 1: Identification**. Ask:\n"
            "- 'Let’s revisit what happened. What was the trigger for your emotion, and how did you interpret that moment?'\n"
            "- 'What emotion came up for you, and how did you feel it in your body or thoughts? Did you feel any urge to act in a certain way?'\n"
            "- 'Can you describe the emotion more precisely—was it sadness, disappointment, hurt, something else? The more we name it, the better we can work with it.'\n"
            
            "Once the user replies, validate their experience with something like:\n"
            "- 'That makes a lot of sense. Feeling [insert emotion] in that situation is completely understandable—thank you for sharing it with me.'\n\n"

            "Then move to **Stage 2: Selection**. Ask:\n"
            f"- 'Let’s think about the two strategies we used today: {first_strat} and {second_strat}. What do you think made them a good fit for what you were going through?'\n"
            "- 'How did it feel to try those two strategies? Were they familiar, or something new? Do you feel like you had a say in using them?'\n\n"

            "Affirm their agency and adaptability:\n"
            "- 'You gave those strategies a real try, and that shows openness and strength. Choosing how to respond—especially when it's hard—is a skill that grows with practice.'\n\n"

            "Then, guide **Stage 3: Implementation**, reflecting on each strategy:\n"
            f"- 'Let’s look at the first strategy {first_strat}. What did you do, and how did it feel as you practiced it? Did anything shift in your body or mind?'\n"
            "- 'Now the second strategy {second_strat}—what did that look like for you? Were you able to notice a change in your thinking or emotions while doing it?'\n"
            "- 'How did the two strategies compare? Did one feel easier, or more effective? Did they support each other in any way?'\n"

            "End by reinforcing growth:\n"
            "- 'You showed a lot of courage by staying with your feelings and trying different ways to meet them. That’s how emotional skill builds—one step at a time.'\n"
            "- 'Whenever you're ready, we can move on to the end of our session. Just type `endphase()` when you feel complete here.'"
        )
    })
    while True:
        msg = input("You: ")
        if is_endphase_command(msg): break
        history.append({"role":"user","content":msg})
        resp = client.chat.completions.create(model="gpt-4.1-mini", messages=history)
        reply = resp.choices[0].message.content.strip()
        history.append({"role":"assistant","content":reply})
        print(f"Aire: {reply}\n")
    summary3 = context_builder(history, primary_emotion, primary_trigger, first_strat, second_strat, 3)
    print(f"[Phase 3 Summary] {summary3}\n")

    print("Aire: Our session is complete. Take care!")



@app.route('/chat', methods=['POST'])
def chat():
    db_session = SessionLocal()
    # Initialize error logging vars with defaults to prevent NameErrors
    participant_id_for_error_log = "N/A"
    current_intervention_id_for_error_log = "N/A"
    
    try:
        data = request.json
        user_message = data.get('message')
        chat_history_from_client = data.get('history', [])
        participant_id = data.get('participant_id')
        is_new_session = data.get('is_new_session', False)

        # Extract the current heart rate at the start of chat
        current_heart_rate = None
        if participant_id:
            # Query the most recent heart rate reading for this participant
            latest_biometric = db_session.query(BiometricData)\
                .filter(BiometricData.participant_id == participant_id)\
                .order_by(BiometricData.timestamp.desc())\
                .first()
            
            if latest_biometric and latest_biometric.heart_rate is not None:
                current_heart_rate = latest_biometric.heart_rate
                print(f"Current heart rate for participant {participant_id}: {current_heart_rate}")
            else:
                print(f"No heart rate data available for participant {participant_id}")



        # Update error log variable as soon as we have the participant_id
        participant_id_for_error_log = participant_id

        if not participant_id:
            print("Error: participant_id missing from request")
            return jsonify({"error": "Participant ID is required."}), 400

        # --- Session & Intervention Handling ---
        if is_new_session:
            # For a new session, the backend calculates the new intervention ID.
            last_id = db_session.query(func.max(Intervention.intervention_id)).filter_by(participant_id=participant_id).scalar()
            current_intervention_id = (last_id or 0) + 1
            
            # Create and save the new intervention record immediately.
            # Include default placeholder values for required fields
            new_intervention = Intervention(
                participant_id=participant_id,
                intervention_id=current_intervention_id,
                conversation_start_time=datetime.datetime.now(ZoneInfo('Europe/Amsterdam')),
                current_phase="1",
                insert_system_prompt="initial"
            )
            db_session.add(new_intervention)
            db_session.commit()
            print(f"--- New session for P_ID {participant_id}, created new record with I_ID: {current_intervention_id} ---")
        else:
            # For an ongoing session, use the ID from the client.
            current_intervention_id = data.get('intervention_id')
            if not current_intervention_id:
                return jsonify({"error": "'intervention_id' is required for an ongoing session."}), 400

            # Defensive check: Make sure the record actually exists.
            intervention_record = db_session.query(Intervention).filter_by(participant_id=participant_id, intervention_id=current_intervention_id).first()
            if not intervention_record:
                # This is a critical fallback. If the client thinks a session is ongoing but the record is missing, we create it.
                print(f"--- WARNING: No record found for ongoing session P_ID {participant_id}, I_ID {current_intervention_id}. Creating it now. ---")
                new_intervention = Intervention(
                    participant_id=participant_id,
                    intervention_id=current_intervention_id,
                    conversation_start_time=datetime.datetime.now(ZoneInfo('Europe/Amsterdam'))
                )
                db_session.add(new_intervention)
                db_session.commit()
                # We now treat it as a new session so it gets the initial system prompt.
                is_new_session = True
            else:
                print(f"--- Ongoing session for P_ID {participant_id}, found record with I_ID: {current_intervention_id} ---")
        
        # Update error log variable now that we have the intervention_id
        current_intervention_id_for_error_log = current_intervention_id

        # chat_history_to_send: Accumulates history for returning to Flutter.
        # Starts with client history, adds current user message, then bot reply.

        chat_history_to_send = list(chat_history_from_client)
        chat_history_to_send.append({"role": "user", "content": user_message})

        # current_history_for_api: What's sent to OpenAI.
        # Starts with client history, adds system prompt if needed, then current user message.
        current_history_for_api = []
        
        intervention_record = db_session.query(Intervention).filter_by(participant_id=participant_id, intervention_id=current_intervention_id).first()
        current_phase = intervention_record.current_phase
        insert_system_prompt = intervention_record.insert_system_prompt
        
        if insert_system_prompt == "initial":
            initial_system_prompt = (
                f"""
                You are Aire, a warm, emotionally attuned therapeutic guide. You're here to support the user in understanding and regulating a difficult emotional experience using the Extended Process Model of Emotion Regulation.
                Start by gently greeting the user and asking for their name. After they respond, greet them using their name and say something like:
                'It’s good to meet you, [Name]. It sounds like there’s something on your mind right now. I’m here to listen. Together, we’ll go through a few gentle steps to help you understand what you’re feeling and what may have triggered it—so you can respond in a way that feels more steady and self-supportive.'

                Let them know that this is the first part of the process: exploring their emotional experience to identify what their emotional patterns look like. This understanding will empower them to recognize and manage their emotions more effectively in the future. Let them know that you will help them gently unpack their experience using the WPVA structure. Give them a short explanation of what this is:

                W (World): We'll explore the **events and circumstances** that led up to you feeling emotional, and what specifically triggered you.

                P (Perception): We'll look at how you **felt in your body** when you experienced these emotions.

                V (Valuation): We'll delve into your **thoughts and values** surrounding the emotional event, and what meaning you made of it.

                A (Action): We'll consider the **actions you took or wanted to take** as a result of this specific emotional experience.

                Then begin Phase 1 by asking a soft, open-ended question like:
                'Let's take that one step at a time. Can you tell me a bit about what’s been present on your mind today—what happened, and how you’ve been feeling in response to it?'

                As the user shares, your job is to help them explore the likely **primary trigger** for their emotional reaction. Triggers may include:
                1. **Somatic trigger** – bodily states like pain, fatigue, or hormonal changes
                2. **Relationship trigger** – conflict, rejection, or abandonment
                3. **Identity trigger** – threat to self-worth, values, or belonging
                4. **Trauma-related trigger** – reactivation of a past traumatic experience
                5. **Existential trigger** – crisis of meaning, loss, or future anxiety
                6. **Environmental/sensory trigger** – noise, smell, weather, or overstimulation

                A more detailed description of each part of the WPVA model to consult when asking the user questions:
                1. World: The context or situation in which the emotional process begins. The “world” provides emotion-eliciting inputs. These are the raw materials from which emotional experiences are constructed.
                2. Perception: Refers to the detection and identification of a physiological, experiential, or situational change—that something emotional is happening. Perception is what the nervous system registers from the world—what was noticed or sensed, either consciously or unconsciously. It includes physiological signals (like a racing heart), sensory impressions (like a facial expression), or the awareness of a thought. Like the world, this part is still largely automatic, but it reflects what entered the person’s awareness rather than what simply occurred.
                3. Valuation: Involves evaluating the significance of that perceived emotion in relation to one’s goals, needs, or context. It’s the meaning-making step where one determines whether the emotion is helpful or harmful, expected or unexpected, appropriate or inappropriate. Valuation is where subjectivity begins. It involves interpreting what was perceived: Is this good or bad for me? Does it threaten something I care about? This step reflects how a person makes meaning of their perception based on personal goals, needs, past experiences, and values. Two people can perceive the same thing but value it differently.
                4. Action: Based on valuation, an action tendency arises (e.g., fight, flee, seek support). So,reacting or regulating based on appraisal/valuation (can be automatic or deliberate). Action refers to the internal or external responses that follow from valuation—such as physiological changes, urges, expressions, or chosen emotion regulation strategies.

                Once you get to the part where you ask the user about their perception, you should mention the user's current heart rate {current_heart_rate} and if its below or above the normal range (70-73). For example, say "Do you notice anything different in your body? For example, I see that your heart rate is {current_heart_rate}, which is higher than average." 

                Once you’re confident about the emotional trigger, affirm your understanding and gently invite the user to move to the next part of the conversation by typing 'endphase()'.

                Do **not** tell the user explicitly which trigger you’ve identified—only that you believe you understand and are ready to help them with regulation next.
                """

            )
            current_history_for_api.append({"role": "system", "content": initial_system_prompt})
            print('\nINITIAL SYSTEM PROMPT ADDED\n')
            intervention_to_update = intervention_record 
            intervention_to_update.insert_system_prompt = "initial"
            try:
                db_session.commit()
                print(f"Intervention record {current_intervention_id} updated with Phase 2a data for P_ID {participant_id}.")
            except Exception as e:
                db_session.rollback()
                print(f"Error updating P2a data for P_ID {participant_id}, I_ID {current_intervention_id}: {e}")
        
        current_history_for_api.extend(chat_history_from_client) 
        current_history_for_api.append({"role": "user", "content": user_message}) 

        bot_reply = ""
        

        if is_endphase_command(user_message): 
                
                print(f"--- Endphase command received for P_ID: {participant_id}, I_ID: {current_intervention_id}, current phase: {current_phase} ---")
                current_phase = intervention_record.current_phase
                
                if current_phase == "1":
                    print(f"Transitioning from Phase 1 to 2 for P_ID: {participant_id}, I_ID: {current_intervention_id}")
                     
                    # --- 1. Extract context for prompts and database (Preserving original logic) ---
                    triggers = extract_trigger_types(current_history_for_api)
                    primary_trigger = triggers[0] if triggers else "unknown"
                    primary_emotion, confidence = identify_emotion_plutchik(current_history_for_api)
                    first_strat, first_prompt, second_strat, second_prompt = decide_strategy(primary_emotion, primary_trigger, current_history_for_api)
                    summary1 = context_builder(current_history_for_api, primary_emotion, primary_trigger, first_strat, second_strat, 1)
                    
                    # --- 2. Update the database record ---
                    try:
                        intervention_to_update = db_session.query(Intervention).filter_by(participant_id=participant_id, intervention_id=current_intervention_id).first()
                        if intervention_to_update:
                            intervention_to_update.summary_phase1 = summary1
                            intervention_to_update.emotion_before = primary_emotion
                            # Convert list of triggers to a comma-separated string
                            intervention_to_update.triggers = ", ".join(triggers) if isinstance(triggers, list) else str(triggers)
                            intervention_to_update.primary_trigger = primary_trigger
                            intervention_to_update.first_strategy = first_strat
                            intervention_to_update.second_strategy = second_strat
                            intervention_to_update.phase2a_start_time = datetime.datetime.now(ZoneInfo('Europe/Amsterdam'))
                            intervention_to_update.insert_system_prompt = "phase2a"
                            intervention_to_update.current_phase = "2a"
                            db_session.commit()
                            print(f"--- Successfully updated P1 data for P_ID {participant_id}, I_ID {current_intervention_id} ---")
                        else:
                            print(f"Error: Could not find intervention record for P_ID {participant_id}, I_ID {current_intervention_id} to update.")
                    except Exception as e:
                        db_session.rollback()
                        print(f"Error updating P1 data for P_ID {participant_id}, I_ID {current_intervention_id}: {e}")

                    # --- 3. Prepare the response for the user --- 
                    bot_reply = f"{summary1}"
                    print('DEBUG: BOT REPLY = SUMMARY 1 FOR CURRENT PHASE = 1')

                    phase2_system_prompt_content = (
                        "You are Aire, a warm, emotionally attuned therapeutic guide. You are now in Phase 2a of the session, focused on implementing the first emotion regulation strategy based on the Extended Process Model. "
                        "Throughout this phase: Maintain a warm, understanding, and curious tone. Help the user explore and apply the strategy, rather than solving their problems directly. Encourage them to discover their own insights. Keep replies concise (max 150 tokens) and conversational, guiding them step-by-step. "
                        f"The user's dominant emotion is: {primary_emotion}. Their identified trigger is: {primary_trigger}.\n"
                        f"You will guide the user through the first strategy: {first_strat}.\n\n"
                        
                        f"FIRST STRATEGY ('{first_strat}'):\n{first_prompt}\n\n"
                    )
                    
                    phase2b_system_prompt_content = (
                            "You are a therapist helping a client regulate their current emotion using the Extended Process Model of Emotion Regulation."
                            "You are now in Phase 2b of the session, focused on implementing the second emotion regulation strategy based on the Extended Process Model. "
                            "Throughout this phase: Maintain a warm, understanding, and curious tone. Help the user explore and apply the strategy, rather than solving their problems directly. Encourage them to discover their own insights. Keep replies concise (max 150 tokens) and conversational, guiding them step-by-step. "
                            f"The user's dominant emotion is: {primary_emotion}. Their identified trigger is: {primary_trigger}.\n"
                            f"You will guide the user through the second strategy: {second_strat}.\n\n"
                            f"SECOND STRATEGY ('{second_strat}'):\n{second_prompt}\n\n"
                    )
                    
                    current_history_for_api.append({"role": "system", "content": phase2_system_prompt_content})

                    # When endphase() is called, we only add the summary to the chat history
                    # This way the user can naturally respond to the summary first
                    chat_history_to_send.append({"role": "assistant", "content": bot_reply})
                    
                    # Store the phase2_system_prompt_content in the session database for later use
                    # We'll retrieve this when the user responds to the summary
                    try:
                        # Make sure intervention_to_update is not None
                        if intervention_to_update is not None:
                            # Check if the attribute exists
                            if hasattr(intervention_to_update, 'phase2_prompt'):
                                intervention_to_update.phase2_prompt = phase2_system_prompt_content
                                intervention_to_update.phase2b_prompt = phase2b_system_prompt_content
                                db_session.commit()
                                print(f"Phase 2 prompts stored for P_ID {participant_id}, I_ID {current_intervention_id}")
                            else:
                                print(f"Warning: intervention_to_update doesn't have phase2_prompt attribute")
                                # Try to commit anyway, maybe the schema is updated but the ORM model is old
                                try:
                                    setattr(intervention_to_update, 'phase2_prompt', phase2_system_prompt_content)
                                    setattr(intervention_to_update, 'phase2b_prompt', phase2b_system_prompt_content)
                                    db_session.commit()
                                    print(f"Added phase2_prompt dynamically for P_ID {participant_id}")
                                except Exception as attr_err:
                                    print(f"Failed to add phase2_prompt dynamically: {attr_err}")
                        else:
                            print(f"Warning: intervention_to_update is None for P_ID {participant_id}")
                    except Exception as e:
                        print(f"Error storing phase2_prompt: {e}")
                        # Continue even if we couldn't store the prompt



                elif current_phase == "2a":                    
                    print(f"Transitioning from Phase 2a to 2b for P_ID: {participant_id}, I_ID: {current_intervention_id}")

                    
                    intervention_record = db_session.query(Intervention).filter_by(participant_id=participant_id, intervention_id=current_intervention_id).order_by(Intervention.intervention_id.desc()).first()
                    if not intervention_record:
                        print(f"Error: No P1 record found for P_ID {participant_id}, I_ID {current_intervention_id} to end Phase 2a.")
                        bot_reply = "Sorry, I encountered an issue retrieving session data. Please try starting a new session."
                        chat_history_to_send.append({"role": "assistant", "content": bot_reply})
                    else:
                        db_primary_emotion = intervention_record.emotion_before
                        db_primary_trigger = intervention_record.primary_trigger
                        db_first_strat = intervention_record.first_strategy
                        db_second_strat = intervention_record.second_strategy
                        summary2a = context_builder(current_history_for_api, db_primary_emotion, db_primary_trigger, db_first_strat, db_second_strat, "2a")
                        bot_reply = "You're doing great! Ready to get into the next strategy?"

                        # Get the second strategy prompt for Phase 2b
                        phase2b_system_prompt_content = intervention_record.phase2b_prompt
                        
                        current_history_for_api.append({"role": "system", "content": phase2b_system_prompt_content})
                        chat_history_to_send.append({"role": "assistant", "content": bot_reply})
                        
                        

                        intervention_to_update = intervention_record 
                        intervention_to_update.summary_phase2a = summary2a
                        emotion_after_p2a, _ = identify_emotion_plutchik(current_history_for_api)
                        intervention_to_update.emotion_after_phase2a = emotion_after_p2a
                        intervention_to_update.phase2b_start_time = datetime.datetime.now(ZoneInfo('Europe/Amsterdam'))
                        intervention_to_update.insert_system_prompt = "phase2b"
                        intervention_to_update.current_phase = "2b"
                        try:
                            db_session.commit()
                            print(f"Intervention record {current_intervention_id} updated with Phase 2a data for P_ID {participant_id}.")
                        except Exception as e:
                            db_session.rollback()
                            print(f"Error updating P2a data for P_ID {participant_id}, I_ID {current_intervention_id}: {e}")

                elif current_phase == "2b":
                    print(f"Transitioning from Phase 2b to 3 for P_ID: {participant_id}, I_ID: {current_intervention_id}")
                    intervention_record = db_session.query(Intervention).filter_by(participant_id=participant_id, intervention_id=current_intervention_id).order_by(Intervention.intervention_id.desc()).first()
                    if not intervention_record:
                        print(f"Error: No P2a record found for P_ID {participant_id}, I_ID {current_intervention_id} to end Phase 2b.")
                        bot_reply = "Sorry, I encountered an issue retrieving session data. Please try starting a new session."
                        chat_history_to_send.append({"role": "assistant", "content": bot_reply})
                    else:
                        db_primary_emotion = intervention_record.emotion_before
                        db_primary_trigger = intervention_record.primary_trigger
                        db_first_strat = intervention_record.first_strategy
                        db_second_strat = intervention_record.second_strategy
                        summary2b = context_builder(current_history_for_api, db_primary_emotion, db_primary_trigger, db_first_strat, db_second_strat, "2b")
                        bot_reply = f"{summary2b}"
                        print('DEBUG: BOT REPLY = SUMMARY 2B FOR CURRENT PHASE = 2B')

                        phase3_system_prompt_content = ('''
                        Ignore the previous system instructions. Follow these new ones. Take note that this is a repeating prompt, so scan the previous conversation to see at which point of the strategy you are to effectively follow the steps.
                        You are a therapist helping a client reflect on their emotion regulation journey using the Extended Process Model of Emotion Regulation by James Gross. 
                        This is the final phase: Guided Reflection. Here, you support the user in consolidating insight from today’s session.\n\n
                        You’ll walk them through the reflection of the session:\n
                        1. **Event Identification** – Revisiting the emotional trigger and the feelings it brought up.\n
                        2. **Strategy Implementation** – Reflecting on the strategy choices.\n
                        Your tone is validating, curious, and gently empowering. You help the user unpack their experience with emotional clarity and build confidence in their regulation skills. 
                        

                        ---

                        ### Starting the Reflection

                        "Welcome to the final part of the session, where we'll take some time to gently reflect on how you moved through your emotions today. There's no rush, so feel free to take your time with each question."

                        ### 1. Reconnecting with the Experience (Event Identification)

                        "Let's start by looking back at the beginning of our session. Can you describe the **trigger** for your emotion, what **emotion** came up for you, and how you experienced it in your body, thoughts, or any urges to act?"

                        (Wait for user's response)

                        "Thank you for sharing that with me. Feeling [insert specific emotion user mentioned, if available; otherwise, use a placeholder like 'that way'] in that situation is completely understandable. It takes courage to revisit that."

                        ---

                        ### 2. Reflecting on Your Strategy Choices (Strategy Selection)

                        "Now, let's shift our focus to the strategies we explored today. We worked with **{db_first_strat}** and **{db_second_strat}**. Thinking back, can you reflect on **what made these strategies a good fit** for what you were going through, and how it felt to engage with them?"

                        (Wait for user's response)

                        "You absolutely gave those strategies a real try, and that truly shows your openness and strength. Choosing how to respond to difficult emotions—especially when it's challenging—is a powerful skill that grows with practice. It speaks to your adaptability."


                        ---

                        ### Final Thoughts and Conclusion

                        "You showed a lot of courage and self-awareness today by staying with your feelings and actively trying different ways to meet them. That's precisely how emotional skill builds—one step at a time, through exploration and reflection. You've gained valuable insight into your own process today.

                        Whenever you're ready, we can end our session. Just type `endphase()` when you feel complete here."
                        ''')

                        current_history_for_api.append({"role": "system", "content": phase3_system_prompt_content})
                        chat_history_to_send.append({"role": "assistant", "content": bot_reply})
                        
                        #current_phase = "3"
                        
                        intervention_to_update = intervention_record 
                        intervention_to_update.phase3_start_time = datetime.datetime.now(ZoneInfo('Europe/Amsterdam'))
                        intervention_to_update.summary_phase2b = summary2b
                        emotion_after_p2b, _ = identify_emotion_plutchik(current_history_for_api)
                        intervention_to_update.phase3_prompt = phase3_system_prompt_content
                        intervention_to_update.insert_system_prompt = "phase3"
                        intervention_to_update.current_phase = "3" 
                        intervention_to_update.emotion_after_phase2b = emotion_after_p2b
                        try:
                            db_session.commit()
                            print(f"Intervention record {current_intervention_id} updated with Phase 2b data for P_ID {participant_id}.")
                        except Exception as e:
                            db_session.rollback()
                            print(f"Error updating P2b data for P_ID {participant_id}, I_ID {current_intervention_id}: {e}")

                elif current_phase == "3":
                    print(f"Transitioning from Phase 3 to End of Session for P_ID: {participant_id}, I_ID: {current_intervention_id}")
                    # The intervention_record is already loaded from the start of the 'endphase' block.
                    # We can reuse it directly instead of performing a redundant query.
                    if not intervention_record:
                        print(f"Error: No P2b record found for P_ID {participant_id}, I_ID {current_intervention_id} to end Phase 3.")
                        bot_reply = "Sorry, I encountered an issue retrieving session data. Please try starting a new session."
                        chat_history_to_send.append({"role": "assistant", "content": bot_reply})
                    else:
                        db_primary_emotion = intervention_record.emotion_before
                        db_primary_trigger = intervention_record.primary_trigger
                        db_first_strat = intervention_record.first_strategy
                        db_second_strat = intervention_record.second_strategy
                        summary3 = context_builder(current_history_for_api, db_primary_emotion, db_primary_trigger, db_first_strat, db_second_strat, 3)
                        

                        session_end_system_prompt = ('''
                            "The session has now concluded. This chat will no longer provide therapeutic guidance. "
                            "You can close this chat window now by typing 'endphase()'."
                        ''')
                        
                        bot_reply = f"{summary3}"

                        chat_history_to_send.insert(-1, {"role": "system", "content": session_end_system_prompt})
                        chat_history_to_send.append({"role": "assistant", "content": bot_reply})

                        intervention_to_update = intervention_record 
                        intervention_to_update.summary_phase3 = summary3
                        emotion_after_p3, _ = identify_emotion_plutchik(current_history_for_api)
                        intervention_to_update.emotion_after_phase3 = emotion_after_p3
                        intervention_to_update.current_phase = "4" 
                        intervention_to_update.conversation_end_time = datetime.datetime.now(ZoneInfo('Europe/Amsterdam'))
                        if intervention_to_update.conversation_start_time:
                            duration = datetime.datetime.now() - intervention_to_update.conversation_start_time
                            intervention_to_update.conversation_duration_seconds = int(duration.total_seconds())
                        else:
                            intervention_to_update.conversation_duration_seconds = None
                            
                        # Save the full chat transcript to the database
                        try:
                            # The chat_history_to_send contains the complete conversation transcript
                            formatted_transcript = json.dumps(chat_history_to_send, indent=2)
                            intervention_to_update.chat_transcript = formatted_transcript
                            print("Chat transcript saved to database")
                        except Exception as e:
                            print(f"Error saving chat transcript: {e}")
                        
                        user_messages_content = [msg['content'] for msg in chat_history_to_send if msg['role'] == 'user']
                        if user_messages_content:
                            total_words = sum(len(str(msg_content).split()) for msg_content in user_messages_content)
                            intervention_to_update.avg_user_input_length_words = total_words / len(user_messages_content)
                        else:
                            intervention_to_update.avg_user_input_length_words = 0.0
                        try:
                            db_session.commit()
                            print(f"Intervention record {current_intervention_id} updated with Phase 3 data for P_ID {participant_id}.")
                        except Exception as e:
                            db_session.rollback()
                            print(f"Error updating P3 data for P_ID {participant_id}, I_ID {current_intervention_id}: {e}")

                        print("--- Conversation ended. Shutting down server. ---")
                        shutdown_func = request.environ.get('werkzeug.server.shutdown')
                        if shutdown_func is None:
                            raise RuntimeError('Not running with the Werkzeug Server')
                        shutdown_func()
                        return 'Server shutting down...' # This response may not be sent as the server is stopping.
                else:
                    print(f"Error: Unknown current_phase '{current_phase}' determined for P_ID {participant_id}, I_ID {current_intervention_id}.")
                    bot_reply = "I seem to have lost my place in our conversation. Could we try starting this section again?"
                    chat_history_to_send.append({"role": "assistant", "content": bot_reply})
                
                # Ensure all components of history are strings before sending
                stringified_history = []
                for message_dict in chat_history_to_send:
                    stringified_message = {str(k): str(v) for k, v in message_dict.items()}
                    stringified_history.append(stringified_message)
                
                return jsonify({
                    'bot_response': [str(bot_reply)],
                    'history': stringified_history,
                    'participant_id': str(participant_id),
                    'intervention_id': str(current_intervention_id)
                })
        
        elif not openai_client:
            bot_reply = "Error: OpenAI client not initialized."
            print("Error: OpenAI client not initialized in /chat endpoint.")
            chat_history_to_send.append({"role": "assistant", "content": str(bot_reply)})
            
            # Ensure all components of history are strings before sending
            stringified_history_error = []
            for message_dict in chat_history_to_send:
                stringified_message = {str(k): str(v) for k, v in message_dict.items()}
                stringified_history_error.append(stringified_message)
            
            # Return error response
            return jsonify({
                "error": "OpenAI client not initialized",
                "bot_response": [str(bot_reply)],
                "history": stringified_history_error,
                "participant_id": str(participant_id),
                "intervention_id": str(current_intervention_id)
            }), 500
        else:
            try:
                # Check if we need to activate Phase 2 - this happens when the user responds to the Phase 1 summary
                if insert_system_prompt == "phase2a":
                    
                    try:
                        # Check the intervention record to see if we have a stored Phase 2 prompt
                        print(f"Checking for Phase 2a prompt for P_ID {participant_id}, I_ID {current_intervention_id}, current phase: {current_phase}")
                        # Use a direct SQL query to avoid ORM issues
                        intervention_record = None
                        try:
                            # First try the ORM way
                            intervention_record = db_session.query(Intervention).filter_by(
                                participant_id=participant_id, 
                                intervention_id=current_intervention_id
                            ).first()
                        except Exception as db_err:
                            print(f"ORM query failed: {db_err}")
                            # ORM failed, let's continue without it
                            pass
                        
                        

                        # Add debug info
                        print(f"Retrieved intervention record in phase2a: {intervention_record is not None}")
                        
                        # Very defensive approach to getting the phase2_prompt
                        if intervention_record is not None:
                            try:
                                if hasattr(intervention_record, 'phase2_prompt'):
                                    phase2_prompt = intervention_record.phase2_prompt
                                    if phase2_prompt:
                                        print(f"Found phase2a_prompt in database for P_ID {participant_id}")
                            except Exception as attr_err:
                                print(f"Error accessing phase2a_prompt: {attr_err}") 
                        
                        if phase2_prompt:
                            # We have a stored Phase 2 prompt from a previous endphase() command
                            # Add the system prompt at the beginning to guide the model properly
                            print(f"Activating Phase 2a prompt for P_ID {participant_id}, I_ID {current_intervention_id}")
                            # Insert system prompt at the beginning, after any existing system prompt
                            system_prompt_inserted = False
                            for i, msg in enumerate(current_history_for_api):
                                if msg['role'] == 'system':
                                    # Replace existing system prompt
                                    current_history_for_api.insert(0, {"role": "system", "content": phase2_prompt})
                                    print('DEBUG: INSERTED SYSTEM PROMPT 2A')
                                    system_prompt_inserted = True
                                    break
                            if not system_prompt_inserted:
                                # No existing system prompt, insert at beginning
                                current_history_for_api.insert(0, {"role": "system", "content": phase2_prompt})
                                print('DEBUG: INSERTED SYSTEM PROMPT 2A')

                        intervention_record.insert_system_prompt = "phase2a"
                        try:
                            db_session.commit()
                            print(f"Intervention record {current_intervention_id} updated with Phase 2a data for P_ID {participant_id}.")
                        except Exception as e:
                            db_session.rollback()
                            print(f"Error updating P2a data for P_ID {participant_id}, I_ID {current_intervention_id}: {e}")
                        
                        else:
                            print(f"No phasea_prompt found for P_ID {participant_id}")
                    except Exception as e:
                        print(f"Error checking phase2_prompt: {e}")
                        # Continue without the prompt
                    

                elif insert_system_prompt == "phase2b":
                    try:
                        # Check the intervention record to see if we have a stored Phase 2 prompt
                        print(f"Checking for Phase 2b prompt for P_ID {participant_id}, I_ID {current_intervention_id}, current phase: {current_phase}")
                        # Use a direct SQL query to avoid ORM issues
                        intervention_record = None
                        try:
                            # First try the ORM way
                            intervention_record = db_session.query(Intervention).filter_by(
                                participant_id=participant_id, 
                                intervention_id=current_intervention_id
                            ).first()
                        except Exception as db_err:
                            print(f"ORM query failed: {db_err}")
                            # ORM failed, let's continue without it
                            pass
                        
                        # Add debug info
                        print(f"Retrieved intervention record in phase2b: {intervention_record is not None}")
                        
                        # Very defensive approach to getting the phase2b_prompt
                        if intervention_record is not None:
                            try:
                                if hasattr(intervention_record, 'phase2b_prompt'):
                                    phase2b_prompt = intervention_record.phase2b_prompt
                                    if phase2b_prompt:
                                        print(f"Found phase2b_prompt in database for P_ID {participant_id}")
                            except Exception as attr_err:
                                print(f"Error accessing phase2b_prompt: {attr_err}")
                        
                        if phase2b_prompt:
                            # We have a stored Phase 2 prompt from a previous endphase() command
                            # Add the system prompt at the beginning to guide the model properly
                            print(f"Activating Phase 2b prompt for P_ID {participant_id}, I_ID {current_intervention_id}")
                            # Insert system prompt at the beginning, after any existing system prompt
                            system_prompt_inserted = False
                            for i, msg in enumerate(current_history_for_api):
                                if msg['role'] == 'system':
                                    # Replace existing system prompt
                                    current_history_for_api[i] = {"role": "system", "content": phase2b_prompt}
                                    print('DEBUG: INSERTED SYSTEM PROMPT 2b')
                                    system_prompt_inserted = True
                                    break
                            if not system_prompt_inserted:
                                # No existing system prompt, insert at beginning
                                current_history_for_api.insert(0, {"role": "system", "content": phase2b_prompt})
                                print('DEBUG: INSERTED SYSTEM PROMPT 2b')
                        else:
                            print(f"No phase2b_prompt found for P_ID {participant_id}")
                    except Exception as e:
                        print(f"Error checking phase2b_prompt: {e}")
                        # Continue without the prompt

                elif insert_system_prompt == "phase3":
                    
                    try:
                        # Check the intervention record to see if we have a stored Phase 2 prompt
                        print(f"Checking for Phase 3 prompt for P_ID {participant_id}, I_ID {current_intervention_id}, current phase: {current_phase}")
                        # Use a direct SQL query to avoid ORM issues
                        intervention_record = None
                        try:
                            # First try the ORM way
                            intervention_record = db_session.query(Intervention).filter_by(
                                participant_id=participant_id, 
                                intervention_id=current_intervention_id
                            ).first()
                        except Exception as db_err:
                            print(f"ORM query failed: {db_err}")
                            # ORM failed, let's continue without it
                            pass
                        
                        

                        # Add debug info
                        print(f"Retrieved intervention record: {intervention_record is not None}")
                        
                        # Very defensive approach to getting the phase2_prompt
                        if intervention_record is not None:
                            try:
                                if hasattr(intervention_record, 'phase3_prompt'):
                                    phase3_prompt = intervention_record.phase3_prompt
                                    if phase3_prompt:
                                        print(f"Found phase3_prompt in database for P_ID {participant_id}")
                            except Exception as attr_err:
                                print(f"Error accessing phase3_prompt: {attr_err}")
                        
                        if phase3_prompt:
                            # We have a stored Phase 3 prompt from a previous endphase() command
                            # Add the system prompt at the beginning to guide the model properly
                            print(f"Activating Phase 3 prompt for P_ID {participant_id}, I_ID {current_intervention_id}")
                            # Insert system prompt at the beginning, after any existing system prompt
                            system_prompt_inserted = False
                            for i, msg in enumerate(current_history_for_api):
                                if msg['role'] == 'system':
                                    # Replace existing system prompt
                                    current_history_for_api.insert(0, {"role": "system", "content": phase3_prompt})
                                    print('DEBUG: INSERTED SYSTEM PROMPT 3')
                                    system_prompt_inserted = True
                                    break
                            if not system_prompt_inserted:
                                # No existing system prompt, insert at beginning
                                current_history_for_api.insert(0, {"role": "system", "content": phase3_prompt})
                                print('DEBUG: INSERTED SYSTEM PROMPT 3')

                        intervention_record.insert_system_prompt = "phase3"
                        try:
                            db_session.commit()
                            print(f"Intervention record {current_intervention_id} updated with Phase 3 data for P_ID {participant_id}.")
                        except Exception as e:
                            db_session.rollback()
                            print(f"Error updating P3 data for P_ID {participant_id}, I_ID {current_intervention_id}: {e}")
                        
                        else:
                            print(f"No phase3_prompt found for P_ID {participant_id}")
                    except Exception as e:
                        print(f"Error checking phase3_prompt: {e}")
                        # Continue without the prompt


                # Now proceed with the normal response generation
                resp = openai_client.chat.completions.create(
                    model="gpt-4.1-mini",
                    messages=current_history_for_api,
                    temperature=0.7,  # Balanced creativity and consistency
                    max_tokens=500,   # Reasonable limit for therapeutic responses
                    top_p=0.9,        # Focus on most likely responses
                    frequency_penalty=0.1,  # Slight penalty to avoid repetition
                    presence_penalty=0.1    # Encourage diverse language
                )
                bot_reply = resp.choices[0].message.content.strip()
                chat_history_to_send.append({"role": "assistant", "content": bot_reply}) # Add full reply to history first
                
                # Split long messages into chunks
                message_chunks = []
                # Split by double newline (paragraphs) first
                if "\n\n" in bot_reply:
                    chunks = bot_reply.split("\n\n")
                    for chunk in chunks:
                        if chunk.strip():  # Avoid empty chunks
                            message_chunks.append(chunk.strip())
                # If no double newlines, but the message is long (e.g., >3 lines or >200 chars), split by single newline
                elif len(bot_reply.split('\n')) > 3 or len(bot_reply) > 200:
                    chunks = bot_reply.split("\n")
                    for chunk in chunks:
                        if chunk.strip():
                            message_chunks.append(chunk.strip())
                
                if not message_chunks:  # If no splitting occurred (e.g., short message)
                    message_chunks.append(bot_reply)

                # Ensure all components of history are strings before sending
                stringified_history_success = []
                for message_dict in chat_history_to_send:
                    stringified_message = {str(k): str(v) for k, v in message_dict.items()}
                    stringified_history_success.append(stringified_message)

                # Ensure bot_response chunks are strings
                stringified_bot_response_chunks = [str(chunk) for chunk in message_chunks]

                response_data = {
                    'bot_response': stringified_bot_response_chunks,
                    'history': stringified_history_success,
                    'participant_id': str(participant_id),
                    'intervention_id': str(current_intervention_id)
                }
                return jsonify(response_data)
            except Exception as e:
                print(f"Error during OpenAI API call for P_ID {participant_id}, I_ID {current_intervention_id}: {e}")
                bot_reply = "Sorry, I encountered an issue trying to process that."
                chat_history_to_send.append({"role":"assistant","content": str(bot_reply)})

                # Ensure all components of history are strings before sending
                stringified_history_error = []
                for message_dict in chat_history_to_send:
                    stringified_message = {str(k): str(v) for k, v in message_dict.items()}
                    stringified_history_error.append(stringified_message)
                
                return jsonify({
                    "reply": str(bot_reply), 
                    "history": stringified_history_error,
                    "participant_id": str(participant_id),
                    "intervention_id": str(current_intervention_id)
                })

    except Exception as e:
        db_session.rollback()
        import traceback
        print(f"--- UNHANDLED EXCEPTION IN /chat FOR P_ID {participant_id_for_error_log}, I_ID {current_intervention_id_for_error_log} ---")
        traceback.print_exc()
        return jsonify({
            "error": "An unexpected server error occurred.",
            "details": str(e),
            "participant_id": str(participant_id_for_error_log),
            "intervention_id": str(current_intervention_id_for_error_log)
        }), 500
    finally:
        db_session.close()


@app.route('/log_biometrics', methods=['POST'])
def log_biometrics():
    """
    Receives and stores continuous biometric data from the wristwatch.
    Expects a JSON payload like:
    {
        "participant_id": "P001",
        "intervention_id": 1,
        "biometrics": [
            {"timestamp": 1678886400000, "hr": 75, "ibi": 800.0, "temp": 34.5},
            {"timestamp": 1678886401000, "hr": 76, "ibi": 789.5, "temp": 34.51}
        ]
    }
    """
    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400

    participant_id = data.get('participant_id')
    intervention_id = data.get('intervention_id')
    biometrics = data.get('biometrics')

    if not all([participant_id, intervention_id, biometrics]):
        return jsonify({"error": "Missing participant_id, intervention_id, or biometrics data"}), 400

    db_session = SessionLocal()
    try:
        for reading in biometrics:
            # Convert timestamp from milliseconds to a timezone-aware datetime object
            ts = datetime.fromtimestamp(reading.get('timestamp') / 1000.0, tz=ZoneInfo('Europe/Amsterdam'))
            
            new_reading = BiometricData(
                participant_id=participant_id,
                intervention_id=intervention_id,
                timestamp=ts,
                heart_rate=reading.get('hr'),
                ibi=reading.get('ibi'),
                skin_temperature=reading.get('temp')
            )
            db_session.add(new_reading)
        
        db_session.commit()
        return jsonify({"status": "success", "message": f"Logged {len(biometrics)} readings."}), 201
    except Exception as e:
        db_session.rollback()
        import traceback
        print(f"Error in /log_biometrics: {e}")
        traceback.print_exc()
        return jsonify({"error": "An error occurred while saving biometric data.", "details": str(e)}), 500
    finally:
        db_session.close()


@app.route('/process_sensor_data', methods=['POST'])
def process_sensor_data():
    model = load_regression_model()
    if model is None:
        return jsonify({"error": "Regression model not loaded. Check server logs."}), 500

    try:
        data = request.json
        if not data:
            return jsonify({"error": "No data provided"}), 400

        ibi_series = data.get('ibi_series_ms')
        skin_temp_series = data.get('skin_temp_series_celsius')
        acc_series = data.get('accelerometer_series') # list of {'x': v, 'y': v, 'z': v}

        if not all([ibi_series, skin_temp_series, acc_series]):
            return jsonify({"error": "Missing one or more sensor data series (ibi_series_ms, skin_temp_series_celsius, accelerometer_series)"}), 400

        hrv_features = calculate_hrv_features(ibi_series)
        skin_temp_features = calculate_skin_temp_features(skin_temp_series)
        acc_features = calculate_accelerometer_features(acc_series)

        # Assemble feature vector in the pre-defined order (29 features)
        # This order MUST match the training order of the model.
        feature_vector_list = [
            hrv_features.get('rmssd', np.nan),
            hrv_features.get('sdnn', np.nan),
            hrv_features.get('pnn50', np.nan),
            hrv_features.get('ibi_mean', np.nan),
            hrv_features.get('ibi_std', np.nan),
            hrv_features.get('hr_mean', np.nan),
            
            skin_temp_features.get('skin_temp_mean', np.nan),
            skin_temp_features.get('skin_temp_std', np.nan),
            skin_temp_features.get('skin_temp_min', np.nan),
            skin_temp_features.get('skin_temp_max', np.nan),
            
            acc_features.get('acc_x_mean', np.nan),
            acc_features.get('acc_y_mean', np.nan),
            acc_features.get('acc_z_mean', np.nan),
            acc_features.get('acc_x_std', np.nan),
            acc_features.get('acc_y_std', np.nan),
            acc_features.get('acc_z_std', np.nan),
            acc_features.get('acc_x_min', np.nan),
            acc_features.get('acc_y_min', np.nan),
            acc_features.get('acc_z_min', np.nan),
            acc_features.get('acc_x_max', np.nan),
            acc_features.get('acc_y_max', np.nan),
            acc_features.get('acc_z_max', np.nan),
            acc_features.get('acc_vm_mean', np.nan),
            acc_features.get('acc_vm_std', np.nan),
            acc_features.get('acc_vm_min', np.nan),
            acc_features.get('acc_vm_max', np.nan),
            acc_features.get('acc_x_energy', np.nan),
            acc_features.get('acc_y_energy', np.nan),
            acc_features.get('acc_z_energy', np.nan)
        ]

        feature_vector = np.array(feature_vector_list, dtype=np.float32).reshape(1, -1) # Reshape to (1, 29)

        if feature_vector.shape[1] != 29:
            return jsonify({"error": f"Feature vector has incorrect shape: {feature_vector.shape}. Expected (1, 29)."}), 500
        
        # Handle potential NaNs - model might not handle them.
        # Simplest strategy: replace NaNs with 0 or mean. For now, let's try with 0.
        # A more robust solution would be imputation based on training data statistics.
        if np.isnan(feature_vector).any():
            print("Warning: NaNs found in feature vector, replacing with 0.")
            feature_vector = np.nan_to_num(feature_vector, nan=0.0)

        prediction = model.predict(feature_vector)
        
        # Assuming the model outputs two values: [valence, arousal]
        valence = float(prediction[0][0])
        arousal = float(prediction[0][1])

        return jsonify({
            "valence": valence,
            "arousal": arousal,
            "raw_prediction": prediction.tolist() # Also send raw for debugging
        })

    except Exception as e:
        import traceback
        print(f"Error in /process_sensor_data: {e}")
        traceback.print_exc()
        return jsonify({"error": "An error occurred while processing sensor data.", "details": str(e)}), 500

def initialize_ai_clients():
    global openai_client, gemini_client
    # --- OpenAI Client Initialization ---
    openai_api_key = os.getenv("OPENAI_KEY")
    if not openai_api_key:
        print("\nFATAL ERROR: 'OPENAI_KEY' environment variable not found.")
        print("Please set the OPENAI_KEY environment variable before running the application.")
        # Exit the application forcefully because it cannot run without the key.
        sys.exit(1)
    
    try:
        openai_client = OpenAI(api_key=openai_api_key)
        print("OpenAI client initialized successfully.")
    except Exception as e:
        print(f"An error occurred during OpenAI client initialization: {e}")
        sys.exit(1)

    # --- Gemini Client Initialization ---
    gemini_api_key = os.getenv("GEMINI_KEY")
    if not gemini_api_key:
        print("\nFATAL ERROR: 'GEMINI_KEY' environment variable not found.")
        print("The Gemini key is required for summary generation. Please set it before running.")
        sys.exit(1)

    try:
        genai.configure(api_key=gemini_api_key)
        # Use a model that's definitely supported in the current API version
        gemini_client = genai.GenerativeModel('gemini-2.0-flash-exp')
        print("Gemini client initialized successfully.")
    except Exception as e:
        print(f"An error occurred during Gemini client initialization: {e}")
        print(f"Available models may have changed. Check Google AI documentation for current model names.")
        sys.exit(1)

@app.route('/store_biometrics', methods=['POST'])
def store_biometrics():
    """Endpoint to receive and store biometric data from the wearable device via mobile app"""
    try:
        data = request.json
        if not data:
            print("Error: No biometric data received")
            return jsonify({"error": "No data provided"}), 400
        
        print(f"[DEBUG] Received biometric data: {data}")
        
        # Extract required fields
        participant_id = data.get('participant_id')
        intervention_id = data.get('intervention_id')
        biometrics = data.get('biometrics', [])
        
        if not participant_id or not intervention_id:
            print("Error: Missing required fields in biometric data")
            return jsonify({"error": "Missing required fields: participant_id or intervention_id"}), 400
        
        if not biometrics:
            print("Warning: Empty biometrics array received")
            return jsonify({"warning": "No biometric readings in payload"}), 200
        
        # Connect to database
        db_session = SessionLocal()
        
        try:
            # Process and store each biometric reading
            readings_added = 0
            for reading in biometrics:
                timestamp = reading.get('timestamp')
                heart_rate = reading.get('hr')
                ibi_array = reading.get('ibi', [])
                skin_temp = reading.get('temp')
                
                # For IBI, we'll store the first value if present
                ibi_value = ibi_array[0] if ibi_array else None
                
                # Create and add a database record
                biometric_record = BiometricData(
                    participant_id=participant_id,
                    intervention_id=intervention_id,
                    timestamp=datetime.datetime.fromtimestamp(timestamp / 1000.0) if timestamp else datetime.datetime.now(),
                    heart_rate=heart_rate,
                    ibi=ibi_value,
                    skin_temperature=skin_temp
                )
                
                db_session.add(biometric_record)
                readings_added += 1
            
            # Commit all changes to the database
            db_session.commit()
            print(f"Successfully stored {readings_added} biometric readings for participant {participant_id}, intervention {intervention_id}")
            
            return jsonify({
                "success": True, 
                "message": f"Successfully stored {readings_added} biometric readings"
            }), 200
            
        except Exception as e:
            db_session.rollback()
            print(f"Database error storing biometric data: {e}")
            return jsonify({"error": f"Database error: {str(e)}"}), 500
        finally:
            db_session.close()
            
    except Exception as e:
        print(f"Error processing biometric data: {e}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500

if __name__ == '__main__':
    initialize_ai_clients()
    load_regression_model() # Load the model at startup
    # Run on port 5001 to avoid conflict with AirPlay or other services on 5000
    app.run(debug=True, host='0.0.0.0', port=5002)
