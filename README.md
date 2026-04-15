# Uhome (U-Tec) Home Assistant Integration

A Home Assistant integration for U-Tec smart home devices via the Uhome API that allows you to control your locks, lights, switches, and sensors through Home Assistant.

## Device Types
- Supports multiple U-tec device types:
    - Locks
    - Lights
    - Switches
    - Smart Plugs (Wifi)
 
### Features
- Secure API communication
- Locking and unlocking
- Lock states
- Door states
- Battery levels
- Switch on and off (Lightbulbs use the switch capabilitiy for some reason, so at very least they should have rudimentary functionality)
- SwitchLevel (Honestly, idk what this is actually for, but hopefully we can use it to control light brightness until they properly implement light controls)

## Limitations
- Currently the Utec API doesn't support the following devices:
	- Wifi bridge modules
	- Air Portal registration / devices

## Requirements
- API Credentials
- External Access Configured (ie., Nabu Casa)

## Ensure Home Assistant knows its own URL
For the Configuration step below to work, Home Assistant must know its own URL.

Navigate to Settings > System > Network and set the Home Assistant URL (Normally `http://homeassistant.local:8123`)

## Getting Your Credentials
#### Having your credentials is necessary to configure the integration, so get them before you install it.
The new process is to activate your API credentials directly in the new XThings app.  From the menu, select your account (the top option with your name and email), then scroll to the bottom and select OpenAPI.  To activate you will be asked what type of role you have (e.g., Developer, Home User, etc), select Home User and the type of device you want to work on. This will automatically activate your account with API credentials and show you your `Client ID`, `Client Secret`, `Scope`, and `RedirectURI`.  

You **must** update the value of `RedirectURI` to `https://my.home-assistant.io/redirect/oauth` from the default of `http://localhost:9501`

For the integration you will need `Client ID` and `Client Secret`.

## Installation
### HACS (Recommended)
Ensure you have [HACS](https://hacs.xyz/docs/use/download/download/) installed\
Open HACS in your Home Assistant instance\
Search for "u-tec" and click on the integration\
Click "Download"\
Restart Home Assistant

### Manual Installation
Download the repository\
Copy the custom_components/Homeassistant-utec folder to your Home Assistant's custom_components directory\
Restart Home Assistant

## Configuration
In Home Assistant, go to Settings > Devices & services > Integrations\
Click the "+ Add integration" button\
Search for "U-Tec"\
You will need to provide the credentials information from above:
- API Scope (leave at the default 'openapi')
- Name (e.g., U-Tec / Ultraloq)
- Client ID
- Client Secret

When you submit, you will be taken to the U-Tec [OAuth site](https://oauth.u-tec.com/login/auth) where you need to login with your U-Tec username and password.  That will then ask you to authorize the OAuth connection.  After that it will take you back to Home Assistant and ask you to link your account to Home Assistant.

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
