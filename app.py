import streamlit as st
import pretty_midi
import cv2
import tempfile
import os
import random
import math

st.title("MIDI同期動画ジェネレーター（pretty_midi・最終安定版）")

# ---------------------------
# MIDI アップロード
# ---------------------------
midi_file = st.file_uploader("MIDIファイルをアップロード", type=["mid", "midi"])

if midi_file:
    temp_midi = tempfile.NamedTemporaryFile(delete=False, suffix=".mid")
    temp_midi.write(midi_file.getbuffer())
    temp_midi.close()

    pm = pretty_midi.PrettyMIDI(temp_midi.name)

    st.subheader("トラック選択")

    track_labels = [
        f"{i}: {inst.name or '名前なし'}（ノート数 {len(inst.notes)}）"
        for i, inst in enumerate(pm.instruments)
    ]

    selected_track = st.radio(
        "使用するトラック",
        range(len(track_labels)),
        format_func=lambda i: track_labels[i]
    )

    notes = sorted(pm.instruments[selected_track].notes, key=lambda n: n.start)
    note_times = [n.start for n in notes]

    st.session_state["note_times"] = note_times
    st.session_state["midi_ready"] = True

# ---------------------------
# 動画アップロード
# ---------------------------
video_file = st.file_uploader("動画ファイルをアップロード", type=["mp4", "mov", "avi"])

if video_file and st.session_state.get("midi_ready"):

    temp_video = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
    temp_video.write(video_file.getbuffer())
    temp_video.close()

    st.video(video_file)

    flip_mode = st.selectbox(
        "左右反転モード",
        ["毎ノート交互に反転", "反転しない", "全ノート反転", "ランダム反転"]
    )

    play_mode = st.selectbox(
        "映像繰り返しモード",
        [
            "1音ごとに映像を繰り返す",
            "映像を終わるまで再生する"
        ]
    )

    LAST_NOTE_MULTIPLIER = st.slider(
        "最後のノートの長さ調整",
        min_value=1.0,
        max_value=3.0,
        value=1.5,
        step=0.1
    )

    if st.button("動画を生成"):

        cap = cv2.VideoCapture(temp_video.name)
        fps = cap.get(cv2.CAP_PROP_FPS)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        total_source_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        # ★ 最後のフレームを1回だけ取得
        cap.set(cv2.CAP_PROP_POS_FRAMES, total_source_frames - 1)
        ret, last_frame = cap.read()
            
        out_path = tempfile.NamedTemporaryFile(
            delete=False, suffix=".mp4").name
        out = cv2.VideoWriter(
            out_path,
            cv2.VideoWriter_fourcc(*"mp4v"),
            fps,
            (w, h)
        )

        note_times = st.session_state["note_times"]

        # ノート間隔 → フレーム数に変換
        note_frames = []
        accum_error = 0.0
        
        for i in range(len(notes)):
        
            if i < len(notes) - 1:
                # 次のノートまで
                duration = notes[i+1].start - notes[i].start
            else:
                # ★ 最後のノートは「実際の長さ」
                duration = notes[i].end - notes[i].start
        
            exact_frames = duration * fps
            base_frames = int(exact_frames)
            frac = exact_frames - base_frames
        
            accum_error += frac
            if accum_error >= 1.0:
                base_frames += 1
                accum_error -= 1.0
        
            note_frames.append(base_frames)

        def should_flip(i):
            if flip_mode == "反転しない":
                return False
            if flip_mode == "全ノート反転":
                return True
            if flip_mode == "毎ノート交互に反転":
                return i % 2 == 1
            if flip_mode == "ランダム反転":
                return random.choice([True, False])
            return False

        st.info("動画生成中…")

        source_frame_index = 0

        for i, frames in enumerate(note_frames):

            if play_mode == "1音ごとに映像を繰り返す":
                source_frame_index = 0

            flip = should_flip(i)

            for _ in range(frames):
                if source_frame_index < total_source_frames:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, source_frame_index)
                    ret, frame = cap.read()
                else:
                    frame = last_frame.copy()
                if not ret:
                    break

                if flip:
                    frame = cv2.flip(frame, 1)

                out.write(frame)
                source_frame_index += 1

        cap.release()
        out.release()

        st.success("動画生成完了！")
        st.video(out_path)

        with open(out_path, "rb") as f:
            st.download_button("動画をダウンロード", f, file_name="output.mp4")
