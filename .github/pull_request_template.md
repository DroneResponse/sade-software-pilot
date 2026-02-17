## Mission Description

<!-- Briefly describe what this pilot does and its intended use case -->

## SADE Features Used

- [ ] Zone-aware navigation (`request_sade_zone_entry`)
- [ ] Custom telemetry via MQTT
- [ ] Multi-drone coordination
- [ ] Custom mission parameters
- [ ] Advanced waypoint planning

## Configuration

<!-- Document any custom settings your pilot accepts -->

Example `custom_settings`:

```json
{
  "parameter_name": "description"
}
```

## Testing

- [ ] Local tests pass: `just test`
- [ ] Code linted: `just lint`
- [ ] Code formatted: `just format`
- [ ] Type checking passes: `just type`

## API Usage

<!-- Confirm you're using SADE APIs correctly -->

- [ ] Uses `ResilientDrone` for autopilot communication
- [ ] Uses `request_sade_zone_entry()` for zone access (if applicable)
- [ ] Handles connection failures gracefully
- [ ] Includes proper error logging

## Documentation

- [ ] Docstrings added to new functions
- [ ] README updated (if applicable)
- [ ] Mission logic is clear and commented

## Deployment

After merge, this pilot will be available as:

```json
{
  "pilot": {
    "repo_url": "https://github.com/YOUR_USERNAME/sade-software-pilot",
    "repo_branch": "contrib/YOUR_USERNAME/BRANCH_NAME"
  }
}
```

## Checklist

- [ ] I have read [CONTRIBUTING.md](CONTRIBUTING.md)
- [ ] No security issues (no unsafe shell invocation, safe file I/O)
- [ ] No secrets or credentials in code
- [ ] Code follows the style guide
- [ ] Changes don't break existing missions

## Additional Notes

<!-- Add any additional context, screenshots, or related issues -->
