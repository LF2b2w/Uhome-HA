# Uhome (U-Tec) Home Assistant Integration

A Home Assistant integration for U-Tec smart home devices via the Uhome API that allows you to control your locks, lights, switches, and sensors through Home Assistant.

## Important
Currently the Utec API doesn't support devices over wifi bridge modules

## Features
- Secure API communication
- Supports multiple U-tec device types:
    - Locks
    - Lights
    - Switches

## Installation
### HACS (Recommended)
Open HACS in your Home Assistant instance\
Click add custom repo\
Paste the URL of this repo and choose type integration\
Search for "U-tec"\
Click "Install"
#### Set up redirect URI in Uhome app
In the Uhome app, under the developer tab -  
    Set redirect URI - `https://my.home-assistant.io/redirect/oauth`

### Manual Installation
Download the repository\
Copy the custom_components/Homeassistant-utec folder to your Home Assistant's custom_components directory\
Restart Home Assistant

## Configuration
In Home Assistant, go to Configuration > Integrations\
Click the "+" button to add a new integration\
Search for "U-Tec"\
You will need to provide:
- Client ID
- Client Secret
- API Scope (default: 'openapi')

## Getting Your Credentials
Visit the U-tec developer portal\
[Apply for developer credentials](https://developer.uhomelabs.com/hc/en-us/requests/new) (They allow end-user, as a reason)\
Note down your:
- Client ID
- Client Secret

In the Uhome app, under the developer tab -  
    Set redirect URI - `https://my.home-assistant.io/redirect/oauth`

## Troubleshooting
See [FAQ](https://github.com/LF2b2w/Uhome-HA/discussions/2)
    
## Contributing
Contributions are welcome! Please feel free to submit a Pull Request.

#### License
This project is licensed under the MIT [License](./LICENSE).

Support
If you encounter any issues or have questions: Check the [Issues](https://github.com/LF2b2w/Uhome-HA/issues) page
Create a new issue if your problem isn't already reported

[Join](https://github.com/LF2b2w/Uhome-HA/discussions) the discussion in the Home Assistant community forums
---
Made with ❤️ by @LF2b2w
