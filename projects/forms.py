from django import forms
from django.utils.text import slugify

from .models import Project


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ["name", "slug", "tagline", "description", "visibility"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5}),
            "visibility": forms.RadioSelect(),
        }

    def __init__(self, *args, owner=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.owner = owner
        self.fields["slug"].required = False
        self.fields["slug"].help_text = "Optional. If empty, generated from name."

    def clean_slug(self):
        raw_slug = (self.cleaned_data.get("slug") or "").strip()
        if raw_slug:
            slug = slugify(raw_slug)
        else:
            slug = slugify(self.cleaned_data.get("name", ""))

        if not slug:
            raise forms.ValidationError("Slug cannot be empty.")

        if self.owner:
            queryset = Project.objects.filter(owner=self.owner, slug=slug)
            if self.instance.pk:
                queryset = queryset.exclude(pk=self.instance.pk)
            if queryset.exists():
                raise forms.ValidationError("This slug is already used for this owner.")

        return slug
