# Uhome (U-Tec) Home Assistant Integration

> **Fork notice:** This is a fork of [LF2b2w/Uhome-HA](https://github.com/LF2b2w/Uhome-HA), the original repository by [@LF2b2w](https://github.com/LF2b2w). The upstream project currently appears to be unmaintained, so this fork exists to keep the integration working. Any changes made here will be offered back to the upstream repository should it become responsive again.

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

API credentials are now available directly in the Xthings Home app (formerly U-Home) version 3.5.5 or later. No need to submit a request through the developer portal.

1. Open the Xthings Home app and go to **My Account**
2. Tap **OpenAPI**
3. Follow the prompts to activate OpenAPI — select your role and the products you are integrating with, then tap **Activate Openapi**

![Steps to enable OpenAPI in the app](images/api_enable_steps.png)

Once activated, you will see your `Client ID`, `Client Secret`, `Scope`, and `RedirectUri`.
- Set `RedirectUri` to `https://my.home-assistant.io/redirect/oauth`
- Confirm `Scope` is set to `OpenAPI`
- Tap **Save**

![API credentials screen](images/api_credentials.png)

For the integration you will need `Client ID` and `Client Secret`.

For more information, see the [Developer API Documentation](https://doc.api.u-tec.com/#intro). If you run into issues with the API, you can [submit a support request](https://developer.xthings.com/hc/en-us/requests/new).

*See [issue #36](https://github.com/LF2b2w/Uhome-HA/issues/36) for more details. Screenshots courtesy of @geofox784.*

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
