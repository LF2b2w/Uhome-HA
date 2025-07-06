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

## Getting Your Credentials
#### Having your credentials is nessecary to configure the integration, so get them before you install it.

Visit the [Developer Portal](https://developer.uhomelabs.com/hc/en-us/requests/new) and login using the same auth you use for your account. 
*Note:* If you get an error about a page not being found, just ignore that and click on *Submit a Request* at the top.

After authenticating, you will *Submit a Request* using the form. For *Request Category* you want to select *API credentials*. In the *Description* be sure to provide the address that is tied to your account to save some back-and-forth with Support. They will send you an NDA to fill out and sign that you must return in order to obtain this ability. Once this is completed it can take a few days to be activated.

*Tip:* Mentioning you are working on a Home Assistant Integration is more than acceptable of a reason for them.

Once your account is activated with API credentials, in your U-Home mobile app there will now be a section called *Develop Console*.  
- There you will find your `Client ID`, `Client Secret`, `Scope`, and `RedirectURI`.
- While you are in there update, or confirm, the value of `RedirectURI` is `https://my.home-assistant.io/redirect/oauth` and `scope` is set to `openapi`. 

For the integration you will need `Client ID` and `Client Secret`.

## Installation
### HACS (Recommended)
Open HACS in your Home Assistant instance\
Click add custom repo\
Paste the URL of this repo and choose type integration\
Search for "U-tec"\
Click "Install"
#### Set up redirect URI in Uhome app
In the Uhome app, in the *Develop Console* tab - \
    Set redirect URI - `https://my.home-assistant.io/redirect/oauth`\
Note: Enter this url exactly as it is here. Do not replace the hostname with your own home assistant.

### Manual Installation
Download the repository\
Copy the custom_components/Homeassistant-utec folder to your Home Assistant's custom_components directory\
Restart Home Assistant

## Configuration
In Home Assistant, go to Configuration > Integrations\
Click the "+" button to add a new integration\
Search for "U-Tec"\
You will need to provide this information from the U-Home mobile app under Settings -> Develop Console :
- Client ID
- Client Secret
- API Scope (default: 'openapi')


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
