from django import forms
from .models import Clearance, Import

class ImportForm(forms.ModelForm):
    file = forms.FileField(
        label='Select a CSV file',
        help_text='Upload a CSV file to import multiple records or leave blank to add a single record.',
        widget=forms.FileInput(attrs={'accept': '.csv'}),
        required=False
    )

    class Meta:
        model = Import
        fields = [
            'file', 'centre', 'department', 'hardware', 'system_model', 'processor',
            'ram_gb', 'hdd_gb', 'serial_number', 'assignee_first_name',
            'assignee_last_name', 'assignee_email_address', 'device_condition',
            'status'
        ]

    def clean_file(self):
        file = self.cleaned_data.get('file')
        if file:
            if not file.name.lower().endswith('.csv'):
                raise forms.ValidationError('Please upload a valid CSV file (.csv extension).')
            max_size = 5 * 1024 * 1024  # 5MB
            if file.size > max_size:
                raise forms.ValidationError(f'File size must be less than {max_size / (1024 * 1024)}MB.')
            if file.size == 0:
                raise forms.ValidationError('The uploaded file is empty.')
        return file
    



class ClearanceForm(forms.ModelForm):
    class Meta:
        model = Clearance
        fields = ['remarks']
        widgets = {
            'remarks': forms.Textarea(attrs={'rows': 4, 'class': 'w-full border rounded-md p-2'}),
        }