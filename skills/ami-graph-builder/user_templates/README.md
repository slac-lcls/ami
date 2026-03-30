# User-Contributed Templates

This directory is for user-created graph templates exported from AMI.

## How to Contribute a Template

1. Build your graph in the AMI GUI
2. Click the "View Source" button in the toolbar
3. Click "Export as Template..."
4. Enter a descriptive name and description
5. Save the template to this directory

## Using Templates

Templates can be loaded and executed in the AMI Console:

```python
# Load a template
exec(open('skills/ami-graph-builder/user_templates/my_template.py').read())

# Run the template
my_template_template()
```

## Template Guidelines

- Use descriptive names that indicate what the graph does
- Add clear TODO comments for parameters that should be customized
- Include example usage in comments
- Document any assumptions about available sources
