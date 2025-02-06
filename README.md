#Uhome-HA Home Assistant Integration

A Home Assistant integration for U-tec smart home devices that allows you to control your U-tec locks, lights, switches, and sensors through Home Assistant.

## Features
OAuth2 authentication support
Supports multiple U-tec device types:
Smart Locks
Smart Lights
Smart Switches
Sensors
Real-time device state updates
Secure API communication

##Installation
### HACS (Recommended)
Open HACS in your Home Assistant instance
Click on "Integrations"
Click the "+" button
Search for "Uhome-HA"
Click "Install"

### Manual Installation
Download the repository
Copy the custom_components/Homeassistant-utec folder to your Home Assistant's custom_components directory
Restart Home Assistant

### Configuration
In Home Assistant, go to Configuration > Integrations
Click the "+" button to add a new integration
Search for "Uhome-HA"
You will need to provide:
Client ID
Client Secret
API Scope (default: 'openapi')

## Getting Your Credentials
Visit the U-tec developer portal
Apply for developer credentials (They allow end-user, as a reason) [https://developer.uhomelabs.com/hc/en-us/requests/new]
Note down your:
Client ID
Client Secret

In the Uhome app, under the developer tab - set redirectURI to https://{External_HA_URL/redirect/oauth | or if you have my HA enabled https://my.home-assistant.io/redirect/oauth

## Supported Devices
U-tec Smart Locks (Door sensor addition TBA)
U-tec Smart Lights
U-tec Smart Switches


## Troubleshooting
### Common Issues
**Authentication Failed**
    Verify your Client ID and Secret
    Ensure your redirect URI is correctly set
    Check if your OAuth tokens are valid
**Device Not Found**
    Confirm the device is properly connected to your U-tec account
    Verify the device is online and accessible
**Integration Not Updating**
    Check your network connection
    Verify the API is accessible
    Restart Home Assistant
    
## Contributing
Contributions are welcome! Please feel free to submit a Pull Request.

Fork the repository
Create your feature branch
Commit your changes
Push to the branch
Open a Pull Request

#### License
This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments
Thanks to U-tec for providing the API
Home Assistant community for support and feedback
All contributors who have helped improve this integration

Support
If you encounter any issues or have questions: Check the Issues page
Create a new issue if your problem isn't already reported
Join the discussion in the Home Assistant community forums
---
Made with ❤️ by @LF2b2w
