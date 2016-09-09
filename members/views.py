import traceback
import string
from datetime import date, datetime, timedelta
from operator import itemgetter, attrgetter
from calendar import Calendar, HTMLCalendar

from django.conf import settings
from django.template import RequestContext, Template, Context
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse, HttpResponseRedirect, HttpResponseForbidden, Http404, HttpRequest
from django.http import JsonResponse
from django.shortcuts import render_to_response, get_object_or_404
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.template.defaultfilters import slugify
from django.contrib.sites.models import Site
from django.contrib import messages
from django.contrib.auth.tokens import default_token_generator

#from gather.models import Event, Location, EventAdminGroup
#from gather.forms import EventForm
#from gather.views import get_location
from interlink.forms import MailingListSubscriptionForm
from interlink.models import IncomingMail
from members.forms import EditProfileForm
from members.models import HelpText, UserNotification
from arpwatch import arp
from arpwatch.models import ArpLog, UserDevice
from nadine.models.core import Member, Membership, DailyLog
from nadine.models.payment import Transaction
from nadine.models.alerts import MemberAlert
from staff import email
from staff.forms import *

from nadine import mailgun
from nadine.utils.slack_api import SlackAPI
from nadine.utils.payment_api import PaymentAPI

def is_active_member(user):
    if user and not user.is_anonymous():
        profile = user.get_profile()
        if profile:
            # If today is their Free Trial Day count them as active
            if DailyLog.objects.filter(user=user, payment='Trial', visit_date=date.today()).count() == 1:
                return True

            # Check to make sure their currently an active member
            return profile.is_active()

    # No user, no profile, no active
    return False


def is_manager(user):
    if user and not user.is_anonymous():
        profile = user.get_profile()
        if profile:
            return profile.is_manager()
    return False

@login_required
def home(request):
    title = "Home"
    template_text = "Welcome to {{ site.name }}"
    other_topics = {}
    for topic in HelpText.objects.all():
        if topic.slug == 'home':
            title = topic.title
            template_text = topic.template
        else:
            other_topics[topic.title] = topic

    current_context = RequestContext(request)
    template = Template(template_text)
    rendered = template.render(current_context)
    return render_to_response('members/home.html', {'title': title, 'page_body': rendered, 'other_topics': other_topics, 'settings': settings}, current_context)

@login_required
def faq(request):
    title = "faq"
    template_text = "Frequently Asked Questions"
    other_topics = {}
    for topic in HelpText.objects.all():
        if topic.slug == 'faq':
            title = topic.title
            template_text = topic.template
        else:
            other_topics[topic.title] = topic

    current_context = RequestContext(request)
    template = Template(template_text)
    rendered = template.render(current_context)
    return render_to_response('members/faq.html', {'title': title, 'page_body': rendered, 'other_topics': other_topics, 'settings': settings}, current_context)

@login_required
def help_topic(request, slug):
    topic = get_object_or_404(HelpText, slug=slug)
    title = topic.title
    template_text = topic.template
    other_topics = HelpText.objects.all().order_by('order')
    current_context = context_instance = RequestContext(request)
    template = Template(template_text)
    rendered = template.render(current_context)
    return render_to_response('members/help_topic.html', {'title': title, 'page_body': rendered, 'other_topics': other_topics, 'settings': settings}, current_context)


@login_required
@user_passes_test(is_active_member, login_url='member_not_active')
def view_members(request):
    active_members = Member.objects.active_members().order_by('user__first_name')
    here_today = Member.objects.here_today()
    has_key = has_mail = None
    if request.user.get_profile().is_manager():
        has_key = Member.objects.members_with_keys()
        has_mail = Member.objects.members_with_mail()

    search_terms = None
    search_results = None
    if request.method == "POST":
        search_form = MemberSearchForm(request.POST)
        if search_form.is_valid():
            search_terms = search_form.cleaned_data['terms']
            search_results = Member.objects.search(search_terms, True)
    else:
        search_form = MemberSearchForm()

    return render_to_response('members/view_members.html', {'settings': settings, 'active_members': active_members, 'here_today': here_today,
                                                            'search_results': search_results, 'search_form': search_form, 'search_terms': search_terms, 'has_key': has_key, 'has_mail': has_mail},
                              context_instance=RequestContext(request))


@login_required
def chat(request):
    user = request.user
    return render_to_response('members/chat.html', {'user': user}, context_instance=RequestContext(request))


def not_active(request):
    return render_to_response('members/not_active.html', {'settings': settings}, context_instance=RequestContext(request))


@login_required
def profile_redirect(request):
    return HttpResponseRedirect(reverse('member_profile', kwargs={'username': request.user.username}))


@login_required
def user(request, username):
    user = get_object_or_404(User, username=username)
    member = user.profile
    activity = DailyLog.objects.filter(user=user, payment='Bill', bills__isnull=True, visit_date__gt=timezone.now().date() - timedelta(days=31))
    guest_activity = DailyLog.objects.filter(guest_of=member, payment='Bill', guest_bills__isnull=True, visit_date__gte=timezone.now().date() - timedelta(days=31))
    emergency_contact = user.get_emergency_contact()
    return render_to_response('members/user.html', {'user': user, 'emergency_contact': emergency_contact, 'activity': activity,
                              'guest_activity': guest_activity, 'settings': settings}, context_instance=RequestContext(request))


@login_required
@user_passes_test(is_active_member, login_url='member_not_active')
def mail(request):
    user = request.user
    if request.method == 'POST':
        sub_form = MailingListSubscriptionForm(request.POST)
        if sub_form.is_valid():
            sub_form.save(user)
            return HttpResponseRedirect(reverse('member_email_lists'))
    return render_to_response('members/mail.html', {'user': user, 'mailing_list_subscription_form': MailingListSubscriptionForm(), 'settings': settings}, context_instance=RequestContext(request))


@login_required
@user_passes_test(is_active_member, login_url='member_not_active')
def mail_message(request, id):
    message = get_object_or_404(IncomingMail, id=id)
    return render_to_response('members/mail_message.html', {'message': message, 'settings': settings}, context_instance=RequestContext(request))


@login_required
def edit_profile(request, username):
    user = get_object_or_404(User, username=username)
    if not user == request.user:
        if not request.user.is_staff:
            return HttpResponseRedirect(reverse('member_profile', kwargs={'username': request.user.username}))

    if request.method == 'POST':
        profile_form = EditProfileForm(request.POST, request.FILES)
        if profile_form.is_valid():
            profile_form.save()
            return HttpResponseRedirect(reverse('member_profile', kwargs={'username': user.username}))
    else:
        profile = user.get_profile()
        emergency_contact = user.get_emergency_contact()
        profile_form = EditProfileForm(initial={'member_id': profile.id, 'first_name': user.first_name, 'last_name': user.last_name, 'email': user.email,
                                                'phone': profile.phone, 'phone2': profile.phone2, 'email2': profile.email2,
                                                'address1': profile.address1, 'address2': profile.address2, 'city': profile.city, 'state': profile.state, 'zipcode': profile.zipcode,
                                                'company_name': profile.company_name, 'url_personal': profile.url_personal, 'url_professional': profile.url_professional,
                                                'url_facebook': profile.url_facebook, 'url_twitter': profile.url_twitter,
                                                'url_linkedin': profile.url_linkedin, 'url_aboutme': profile.url_aboutme, 'url_github': profile.url_github,
                                                'bio': profile.bio, 'photo': profile.photo,
                                                'public_profile': profile.public_profile,
                                                'gender': profile.gender, 'howHeard': profile.howHeard, 'industry': profile.industry, 'neighborhood': profile.neighborhood,
                                                'has_kids': profile.has_kids, 'self_employed': profile.self_employed,
                                                'emergency_name': emergency_contact.name, 'emergency_relationship': emergency_contact.relationship,
                                                'emergency_phone': emergency_contact.phone, 'emergency_email': emergency_contact.email,

                                            })

    return render_to_response('members/edit_profile.html', {'user': user, 'profile_form': profile_form, 'ALLOW_PHOTO_UPLOAD': settings.ALLOW_PHOTO_UPLOAD, 'settings': settings}, context_instance=RequestContext(request))


@login_required
def slack(request, username):
    user = get_object_or_404(User, username=username)
    if not user == request.user:
        if not request.user.is_staff:
            return HttpResponseRedirect(reverse('member_profile', kwargs={'username': request.user.username}))

    if request.method == 'POST':
        try:
            slack_api = SlackAPI()
            slack_api.invite_user(user)
            messages.add_message(request, messages.INFO, "Slack Invitation Sent.  Check your email for further instructions.")
        except Exception as e:
            messages.add_message(request, messages.ERROR, "Failed to send invitation: %s" % e)

    return render_to_response('members/slack.html', {'user': user, 'team_url':settings.SLACK_TEAM_URL, 'settings': settings}, context_instance=RequestContext(request))

@csrf_exempt
def slack_bots(request):
    # Stupid chat bot
    try:
        text = request.POST.get("text")[7:]
        SlackAPI().post_message(text)
    except Exception as e:
        return JsonResponse({'text': str(e)})
    return JsonResponse({})

@login_required
def receipt(request, username, id):
    user = get_object_or_404(User, username=username)
    if not user == request.user:
        if not request.user.is_staff:
            return HttpResponseRedirect(reverse('member_profile', kwargs={'username': request.user.username}))

    transaction = get_object_or_404(Transaction, id=id)
    if not user == transaction.user:
        if not request.user.is_staff:
            return HttpResponseRedirect(reverse('member_profile', kwargs={'username': request.user.username}))
    bills = transaction.bills.all()
    return render_to_response('members/receipt.html', {'user': user, 'transaction': transaction, 'bills': bills, 'settings': settings}, context_instance=RequestContext(request))


@login_required
@user_passes_test(is_active_member, login_url='member_not_active')
def tags(request):
    tags = []
    for tag in Member.tags.all().order_by('name'):
        members = Member.objects.active_members().filter(tags__name__in=[tag])
        if members:
            tags.append((tag, members))
    return render_to_response('members/tags.html', {'tags': tags, 'settings': settings}, context_instance=RequestContext(request))


@login_required
@user_passes_test(is_active_member, login_url='member_not_active')
def tag_cloud(request):
    tags = []
    for tag in Member.tags.all().order_by('name'):
        members = Member.objects.active_members().filter(tags__name__in=[tag])
        if members:
            tags.append((tag, members))
    return render_to_response('members/tag_cloud.html', {'tags': tags, 'settings': settings}, context_instance=RequestContext(request))


@login_required
@user_passes_test(is_active_member, login_url='member_not_active')
def tag(request, tag):
    members = Member.objects.active_members().filter(tags__name__in=[tag])
    return render_to_response('members/tag.html', {'tag': tag, 'members': members, 'settings': settings}, context_instance=RequestContext(request))


@login_required
def user_tags(request, username):
    user = get_object_or_404(User, username=username)
    if not user == request.user:
        if not request.user.is_staff:
            return HttpResponseRedirect(reverse('member_profile', kwargs={'username': request.user.username}))
    profile = user.get_profile()
    user_tags = profile.tags.all()

    error = None
    if request.method == 'POST':
        tag = request.POST.get('tag')
        if tag:
            for p in string.punctuation:
                if p in tag:
                    error = "Tags can't contain punctuation."
                    break
            else:
                profile.tags.add(tag.lower())

    all_tags = Member.tags.all()
    return render_to_response('members/user_tags.html', {'user': user, 'user_tags': user_tags, 'all_tags': all_tags, 'error': error, 'settings': settings}, context_instance=RequestContext(request))


@login_required
def delete_tag(request, username, tag):
    user = get_object_or_404(User, username=username)
    if not user == request.user:
        if not request.user.is_staff:
            return HttpResponseRedirect(reverse('member_profile', kwargs={'username': request.user.username}))
    user.get_profile().tags.remove(tag)
    return HttpResponseRedirect(reverse('member_user_tags', kwargs={'username': username, 'settings': settings}))


@login_required
def user_devices(request, username):
    user = get_object_or_404(User, username=username)
    if not user == request.user:
        if not request.user.is_staff:
            return HttpResponseRedirect(reverse('member_profile', kwargs={'username': request.user.username}))
    profile = user.get_profile()

    error = None
    if request.method == 'POST':
        device_id = request.POST.get('device_id')
        device = UserDevice.objects.get(id=device_id)

        action = request.POST.get('action')
        if action == "Register":
            device.user = user

        device_name = request.POST.get('device_name')
        device_name = device_name.strip()[:32]
        device.device_name = device_name
        device.save()

    devices = arp.devices_by_user(user)
    ip = request.META['REMOTE_ADDR']
    this_device = arp.device_by_ip(ip)
    return render_to_response('members/user_devices.html', {'user': user, 'devices': devices, 'this_device': this_device, 'ip': ip, 'error': error, 'settings': settings}, context_instance=RequestContext(request))


@login_required
@user_passes_test(is_active_member, login_url='member_not_active')
def connect(request, username):
    message = ""
    target = get_object_or_404(User, username=username)
    user = request.user
    action = request.GET.get('action')
    if action and action == "send_info":
        email.send_contact_request(user, target)
        message = "Email Sent"
    return render_to_response('members/connect.html', {'target': target, 'user': user, 'page_message': message, 'settings': settings}, context_instance=RequestContext(request))


@login_required
def notifications(request):
    notifications = UserNotification.objects.filter(notify_user=request.user, sent_date__isnull=True)
    return render_to_response('members/notifications.html', {'notifications': notifications}, context_instance=RequestContext(request))


@login_required
def add_notification(request, username):
    target = get_object_or_404(User, username=username)
    if UserNotification.objects.filter(notify_user=request.user, target_user=target, sent_date__isnull=True).count() == 0:
        UserNotification.objects.create(notify_user=request.user, target_user=target)
    return HttpResponseRedirect(reverse('member_notifications', kwargs={}))


@login_required
def delete_notification(request, username):
    target = get_object_or_404(User, username=username)
    for n in UserNotification.objects.filter(notify_user=request.user, target_user=target):
        n.delete()
    return HttpResponseRedirect(reverse('member_notifications', kwargs={}))


@login_required
def disable_billing(request, username):
    user = get_object_or_404(User, username=username)
    if user == request.user or request.user.is_staff:
        api = PaymentAPI()
        api.disable_recurring(username)
        email.announce_billing_disable(user)
    return HttpResponseRedirect(reverse('member_profile', kwargs={'username': request.user.username, 'settings': settings}))


@login_required
@user_passes_test(is_active_member, login_url='member_not_active')
def events_google(request, location_slug=None):
    return render_to_response('members/events_google.html', {'settings': settings}, context_instance=RequestContext(request))


@login_required
@user_passes_test(is_active_member, login_url='member_not_active')
def file_view(request, disposition, username, file_name):
    if not request.user.is_staff and not username == request.user.username:
        return HttpResponseForbidden("Forbidden")
    file_upload = FileUpload.objects.filter(user__username=username, name=file_name).first()
    if not file_upload:
        raise Http404
    if disposition == None or not (disposition == "inline" or disposition == "attachment"):
        disposition = "inline"
    response = HttpResponse(file_upload.file, content_type=file_upload.content_type)
    response['Content-Disposition'] = '%s; filename="%s"' % (disposition, file_upload.name)
    return response


@csrf_exempt
@login_required
@user_passes_test(is_manager, login_url='member_not_active')
def manage_member(request, username):
    user = get_object_or_404(User, username=username)

    # Handle the buttons if a task is being marked done
    if request.method == 'POST':
        #print(request.POST)
        if 'resolve_task' in request.POST:
            alert = MemberAlert.objects.get(pk=request.POST.get('alert_id'))
            alert.resolve(request.user)

    # Render the email content in to a variable to make up the page content
    text_content, html_content = mailgun.get_manage_member_content(user)

    return render_to_response('members/manage_member.html', {'user': user, 'page_content': html_content}, context_instance=RequestContext(request))

def register(request):
    page_message = None
    if request.method == 'POST':
        registration_form = NewUserForm(request.POST)
        try:
            if registration_form.is_valid():
                user = registration_form.save()
                token = default_token_generator.make_token(user)
                path = 'Ng-' + token + '/'
                return HttpResponseRedirect(reverse('password_reset')+ path)
        except Exception as e:
            page_message = str(e)
            logger.error(str(e))
    else:
        registration_form = NewUserForm()
    return render_to_response('members/register.html', { 'registration_form': registration_form, 'page_message': page_message, 'settings': settings}, context_instance=RequestContext(request))

#@login_required
#@user_passes_test(is_active_member, login_url='member_not_active')
# def my_create_event(request, location_slug=None):
#	return create_event(request, location_slug)

# Copyright 2014 Office Nomads LLC (http://www.officenomads.com/) Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the License. You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0 Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the specific language governing permissions and limitations under the License.
