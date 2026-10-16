from django import forms
from django.contrib import admin, messages
from django.contrib.auth.models import Group
from django.shortcuts import redirect, render
from unfold.admin import ModelAdmin

from .logic.corpus import text_from_upload
from .logic.settings import load_config
from .models import LibraryText


class LibraryTextForm(forms.ModelForm):
    """Paste the text, or upload a .txt/.md file and let the app fill in the body (and language)."""

    file = forms.FileField(
        required=False,
        label="Upload a file",
        help_text="A .txt or .md file. If you upload one, it replaces the body above; the language is detected if left blank.",
    )

    class Meta:
        model = LibraryText
        fields = "__all__"
        widgets = {"body": forms.Textarea(attrs={"rows": 14})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["body"].required = False
        self.fields["title"].required = False

    def clean(self):
        data = super().clean()
        upload = data.get("file")
        if upload:
            parsed = text_from_upload(upload.name, upload.read(), load_config())
            data["body"] = parsed.body
            if not data.get("title"):
                data["title"] = parsed.title
        if not (data.get("title") or "").strip():
            self.add_error("title", "Give the text a title (or upload a file to use its name).")
        if not (data.get("body") or "").strip():
            self.add_error("body", "Paste the text or upload a file.")
        return data


class GroupChoiceForm(forms.Form):
    group = forms.ModelChoiceField(queryset=Group.objects.order_by("name"))


@admin.register(LibraryText)
class LibraryTextAdmin(ModelAdmin):
    form = LibraryTextForm
    list_display = ("source_ref", "title", "language_name", "author", "level", "group_names", "active")
    list_filter = ("language_name", "active", "groups")
    search_fields = ("source_ref", "title", "author")
    filter_horizontal = ("groups",)
    list_per_page = 50
    readonly_fields = ("lang", "language_name", "script")
    actions = ["add_to_group", "remove_from_group", "activate", "deactivate"]

    @admin.display(description="Groups")
    def group_names(self, obj):
        return ", ".join(g.name for g in obj.groups.all()) or "everyone signed in"

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("groups")

    def _choose_group(self, request, queryset, verb: str, action: str):
        """Two-step action: ask which group, then apply to the selected texts."""
        if "apply" in request.POST:
            form = GroupChoiceForm(request.POST)
            if form.is_valid():
                group = form.cleaned_data["group"]
                for text in queryset:
                    (text.groups.add if action == "add_to_group" else text.groups.remove)(group)
                self.message_user(
                    request,
                    f"{verb} {queryset.count()} text(s) {'to' if action == 'add_to_group' else 'from'} {group.name}.",
                    messages.SUCCESS,
                )
                return redirect(request.get_full_path())
        else:
            form = GroupChoiceForm()
        return render(request, "admin/reading/librarytext/choose_group.html", {
            **self.admin_site.each_context(request),
            "title": f"{verb} group",
            "form": form,
            "texts": queryset,
            "action": action,
            "verb": verb,
            "action_checkbox_name": admin.helpers.ACTION_CHECKBOX_NAME,
            "opts": self.model._meta,
        })

    @admin.action(description="Add selected texts to a group...")
    def add_to_group(self, request, queryset):
        return self._choose_group(request, queryset, "Added", "add_to_group")

    @admin.action(description="Remove selected texts from a group...")
    def remove_from_group(self, request, queryset):
        return self._choose_group(request, queryset, "Removed", "remove_from_group")

    @admin.action(description="Activate selected texts")
    def activate(self, request, queryset):
        self.message_user(request, f"Activated {queryset.update(active=True)} text(s).")

    @admin.action(description="Deactivate selected texts (hide from readers)")
    def deactivate(self, request, queryset):
        self.message_user(request, f"Deactivated {queryset.update(active=False)} text(s).")
