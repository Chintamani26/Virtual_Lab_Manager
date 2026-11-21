import os
import time
import glob
import subprocess
from playwright.sync_api import sync_playwright
import imageio_ffmpeg

def record():
    recordings_dir = os.path.abspath("recordings")
    os.makedirs(recordings_dir, exist_ok=True)
    
    # Clean previous recordings
    for f in glob.glob(os.path.join(recordings_dir, "*.*")):
        try:
            os.remove(f)
        except Exception:
            pass
            
    print("Launching Chromium to record demo walkthrough...")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            headless=True
        )
        context = browser.new_context(
            record_video_dir=recordings_dir,
            record_video_size={"width": 1280, "height": 720},
            viewport={"width": 1280, "height": 720}
        )
        page = context.new_page()
        
        # Helper for smooth sleep and logging
        def wait_and_log(sec, message):
            print(f"[{time.strftime('%H:%M:%S')}] {message} ({sec}s)")
            page.wait_for_timeout(sec * 1000)

        # =====================================================================
        # SCENE 1: LANDING & LOGIN (0:00 - 0:20)
        # =====================================================================
        page.goto("http://localhost:3000")
        wait_and_log(3, "Land on dark modern login page")
        
        # Smooth scroll down to highlight 1-click persona options
        page.mouse.wheel(0, 300)
        wait_and_log(2, "Showcase 1-Click Judging Persona switcher")
        page.mouse.wheel(0, -300)
        wait_and_log(1, "Scroll back to view")
        
        # Click Student Demo
        student_btn = page.locator("button:has-text('Student')").first
        student_btn.hover()
        wait_and_log(1.5, "Hover on Student Demo persona (Aarav Sharma)")
        student_btn.click()
        page.wait_for_url("**/student**")
        wait_and_log(3, "Landed on Student Dashboard")

        # =====================================================================
        # SCENE 2: STUDENT DASHBOARD & LAB NAVIGATION (0:20 - 0:45)
        # =====================================================================
        # Scroll dashboard to show courses and metrics
        page.mouse.wheel(0, 250)
        wait_and_log(2.5, "Explore enrolled courses: CS201 Data Structures, EE210, MA201, PH101")
        page.mouse.wheel(0, 300)
        wait_and_log(2.5, "Inspect practicals list and completion badges")
        
        # Click on a practical
        lab_link = page.locator("a[href*='/student/labs/']").first
        if lab_link.count() > 0:
            lab_link.hover()
            wait_and_log(1, "Selecting practical workspace")
            lab_link.click()
        else:
            page.goto("http://localhost:3000/student/labs/21dd5914-83eb-587f-85b1-d3d489ce3a7a")
            
        page.wait_for_url("**/student/labs/**")
        wait_and_log(4, "Loaded Student Dual-Pane Lab Workspace")

        # Handle Proctor/Start Gate if present
        gate = page.locator("[data-testid='proctor-gate']")
        if gate.count() > 0:
            print("Found Proctor Start Gate — acknowledging instructions...")
            ack_cb = page.locator("[data-testid='gate-ack']")
            if ack_cb.count() > 0:
                ack_cb.check()
                wait_and_log(1, "Checked acknowledgment box")
            start_btn = page.locator("button:has-text('Start')").first
            if start_btn.count() > 0:
                start_btn.click()
                wait_and_log(2, "Started proctored lab session")

        # =====================================================================
        # SCENE 3: STUDENT DUAL-PANE WORKSPACE & GEMINI TUTOR (0:45 - 1:25)
        # =====================================================================
        # Show code editor
        wait_and_log(2, "Reviewing Python Linked List code in Monaco Editor")
        
        # Run tests
        run_btn = page.locator("button:has-text('Run tests')").first
        if run_btn.count() > 0:
            run_btn.hover()
            wait_and_log(1, "Clicking 'Run tests' button")
            run_btn.click()
            wait_and_log(3.5, "Test runner executing in sandboxed runner...")
            
        # Open Gemini Socratic AI Tutor
        ai_btn = page.locator("button:has-text('AI Hint')").first
        if ai_btn.count() > 0:
            ai_btn.hover()
            wait_and_log(1, "Clicking '✨ AI Hint' to trigger Gemini Socratic Tutor")
            ai_btn.click()
            wait_and_log(2, "Gemini Tutor drawer opened")
            
        # Type in tutor box if available
        tutor_input = page.locator("input[placeholder*='Ask'], textarea[placeholder*='Ask']").first
        if tutor_input.count() > 0:
            tutor_input.fill("How do I properly reverse pointers when reversing a singly linked list?")
            wait_and_log(1.5, "Typing question to Socratic AI Tutor")
            send_btn = page.locator("button:has-text('Send'), button[type='submit']").first
            if send_btn.count() > 0:
                send_btn.click()
                wait_and_log(4, "Gemini generating pedagogical Socratic hint...")
        else:
            wait_and_log(3, "Inspecting Socratic guidance conversation thread")

        # View Rubric tab
        rubric_tab = page.locator("button:has-text('Rubric')").first
        if rubric_tab.count() > 0:
            rubric_tab.click()
            wait_and_log(2.5, "Inspecting automated rubric score breakdown")

        # Submit Practical
        submit_btn = page.locator("button:has-text('Submit for Auto-Grade')").first
        if submit_btn.count() > 0:
            submit_btn.hover()
            wait_and_log(1, "Clicking 'Submit for Auto-Grade'")
            submit_btn.click()
            wait_and_log(3, "Practical submitted for automated grading")

        # =====================================================================
        # SCENE 4: FACULTY ROLE & REAL-TIME LAB MONITOR (1:25 - 1:55)
        # =====================================================================
        # Clear session to return cleanly to landing page
        wait_and_log(1.5, "Transitioning from Student to Faculty Persona")
        page.evaluate("() => { localStorage.clear(); sessionStorage.clear(); window.location.href = '/'; }")
        page.wait_for_url("http://localhost:3000/")
        wait_and_log(2, "On Landing Page — Selecting Faculty Demo (Meera Kulkarni)")
        
        faculty_btn = page.locator("button:has-text('Faculty')").first
        faculty_btn.hover()
        wait_and_log(1, "Hovering on Faculty Demo")
        faculty_btn.click()
        page.wait_for_url("**/faculty**")
        wait_and_log(3, "Landed on Faculty Control Center")

        # Explore Faculty dashboard metrics
        page.mouse.wheel(0, 250)
        wait_and_log(2.5, "Reviewing active practicals, submissions, and alerts")
        
        # Navigate to monitor or submissions
        monitor_link = page.locator("a[href*='/monitor'], button:has-text('Monitor')").first
        if monitor_link.count() > 0:
            monitor_link.click()
            wait_and_log(3.5, "Viewing Real-Time Student Lab Monitor grid")
            page.go_back()
            wait_and_log(1, "Returned to Faculty overview")
            
        # Navigate to New practical creator
        new_prac_btn = page.locator("a[href*='/practicals/new']").first
        if new_prac_btn.count() > 0:
            new_prac_btn.click()
            page.wait_for_url("**/practicals/new**")
            wait_and_log(3, "Faculty AI Practical Generator & Syllabus Builder")
            page.go_back()
            wait_and_log(1, "Returned to Faculty overview")

        # =====================================================================
        # SCENE 5: HOD ROLE & DEPARTMENT COMPLIANCE (1:55 - 2:20)
        # =====================================================================
        wait_and_log(1.5, "Transitioning from Faculty to HOD Persona")
        page.evaluate("() => { localStorage.clear(); sessionStorage.clear(); window.location.href = '/'; }")
        page.wait_for_url("http://localhost:3000/")
        wait_and_log(2, "On Landing Page — Selecting HOD Demo (Dr. Rajesh Deshpande)")
        
        hod_btn = page.locator("button:has-text('HOD')").first
        hod_btn.hover()
        wait_and_log(1, "Hovering on HOD Demo")
        hod_btn.click()
        page.wait_for_url("**/hod**")
        wait_and_log(3, "Landed on HOD Department Governance Dashboard")

        # Scroll HOD metrics
        page.mouse.wheel(0, 250)
        wait_and_log(3, "Reviewing Department Compliance Scorecard & Macro Metrics")
        page.mouse.wheel(0, 300)
        wait_and_log(3, "Reviewing Student Learning Difficulties & Concept Heatmap")
        
        # Hover Export CSV
        csv_btn = page.locator("button:has-text('Export'), a:has-text('Export')").first
        if csv_btn.count() > 0:
            csv_btn.hover()
            wait_and_log(2, "Hover on 'Export Compliance CSV' for NBA/NAAC accreditation")

        # =====================================================================
        # SCENE 6: WRAP UP (2:20 - 2:30)
        # =====================================================================
        page.evaluate("() => { localStorage.clear(); sessionStorage.clear(); window.location.href = '/'; }")
        page.wait_for_url("http://localhost:3000/")
        wait_and_log(3, "Completed full platform walkthrough of all 3 roles")
        
        context.close()
        browser.close()
        print("Browser closed. Video finalized.")

    # Find the generated video file
    video_files = glob.glob(os.path.join(recordings_dir, "*.webm"))
    if not video_files:
        print("Error: No video file found in recordings directory.")
        return

    raw_video = video_files[0]
    out_mp4 = os.path.abspath("Virtual_Lab_Manager_Full_Walkthrough.mp4")
    out_webm = os.path.abspath("Virtual_Lab_Manager_Full_Walkthrough.webm")
    dl_mp4 = r"C:\Users\Chintamani\Downloads\Virtual_Lab_Manager_Full_Walkthrough.mp4"
    
    # Save standard webm
    if os.path.exists(out_webm):
        try: os.remove(out_webm)
        except: pass
    import shutil
    shutil.copyfile(raw_video, out_webm)
    print(f"Saved raw WebM to: {out_webm}")

    # Convert to MP4 using imageio-ffmpeg
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    print(f"Converting video to MP4 using ffmpeg ({ffmpeg_exe})...")
    cmd = [
        ffmpeg_exe, "-y",
        "-i", raw_video,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "22",
        "-pix_fmt", "yuv420p",
        out_mp4
    ]
    subprocess.run(cmd, check=True)
    print(f"Successfully generated MP4 video at: {out_mp4}")
    
    # Copy to Downloads
    try:
        shutil.copyfile(out_mp4, dl_mp4)
        print(f"Copied MP4 to Downloads at: {dl_mp4}")
    except Exception as e:
        print("Note on Downloads copy:", e)

if __name__ == "__main__":
    record()
