from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group, User
from django.db import transaction
from unfold.admin import ModelAdmin, StackedInline
from unfold.forms import AdminPasswordChangeForm, UserChangeForm

from .models import AllowedLogin, GroupAccess
from .services import send_account_created_email

admin.site.unregister(User)
admin.site.unregister(Group)


class InviteUserForm(forms.ModelForm):
    """Create an account with no password; the person sets their own via the
    emailed link. Username is always the lower-cased email."""

    email = forms.EmailField()

    class Meta:
        model = User
        fields = ("email", "first_name", "last_name")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(username=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = user.email = self.cleaned_data["email"]
        user.set_unusable_password()
        if commit:
            user.save()
            self.save_m2m()
        return user


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    form = UserChangeForm
    change_password_form = AdminPasswordChangeForm
    add_form = InviteUserForm
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "first_name", "last_name")}),)
    list_display = ("username", "first_name", "last_name", "is_staff", "is_active")
    actions = ["resend_set_password_email"]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change and settings.EMAIL_PASSWORD_LOGIN_ENABLED:
            transaction.on_commit(lambda: send_account_created_email(obj, request))

    @admin.action(description="Send set-password email")
    def resend_set_password_email(self, request, queryset):
        if not settings.EMAIL_PASSWORD_LOGIN_ENABLED:
            self.message_user(request, "Email/password login is not enabled.", messages.WARNING)
            return
        for user in queryset.exclude(email=""):
            send_account_created_email(user, request)
        self.message_user(request, "Set-password emails sent.")


class GroupAccessInline(StackedInline):
    model = GroupAccess
    max_num = 1
    can_delete = False
    verbose_name = "Text access"
    verbose_name_plural = "Text access"


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    inlines = [GroupAccessInline]
    list_display = ("name", "sees_all_texts", "text_count", "user_count")

    @admin.display(boolean=True, description="Sees every text")
    def sees_all_texts(self, obj):
        access = getattr(obj, "access", None)
        return bool(access and access.sees_all_texts)

    @admin.display(description="Texts limited to this group")
    def text_count(self, obj):
        return obj.library_texts.count()

    @admin.display(description="Users")
    def user_count(self, obj):
        return obj.user_set.count()


@admin.register(AllowedLogin)
class AllowedLoginAdmin(ModelAdmin):
    list_display = ("identifier", "matched_user", "group_names", "created_at")
    search_fields = ("identifier",)
    filter_horizontal = ("groups",)

    @admin.display(description="Groups")
    def group_names(self, obj):
        return ", ".join(g.name for g in obj.groups.all()) or "-"
