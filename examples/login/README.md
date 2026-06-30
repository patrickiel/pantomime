# Pantomime Login Example

This is a small "Login" application and test suite shipped as a test target for Pantomime. 
It demonstrates testing a Tkinter application where fields cannot be read by standard Windows UI Automation, showing how Pantomime's local OpenCV and OCR grounding fallback works.

## Running the Example

1. Ensure your `config/pantomime.yaml` is configured with a reasoning API key.
2. Open a terminal and run the demo application:
   ```powershell
   uv run python examples/login/fixtures/login_app.py
   ```
3. Open a second terminal and run the Pantomime test suite against the Login window. You can run it via the CLI:
   ```powershell
   panto runner
   ```
   **Alternatively**, you can step through the CLI:
   ```powershell
   panto run examples/login/tests/login.yaml --window Login
   ```
