import string
import traceback
from datetime import date, datetime, timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse, HttpResponseRedirect, HttpResponseForbidden, Http404, HttpRequest
from django.shortcuts import render, get_object_or_404
from django.utils import timezone

from nadine.models.core import UserProfile
from nadine.models.organization import Organization

from members.views.core import is_active_member


@login_required
@user_passes_test(is_active_member, login_url='member_not_active')
def tags(request):
    tags = []
    for tag in UserProfile.tags.all().order_by('name'):
        members = User.helper.members_with_tag(tag)
        if members.count() > 0:
            tags.append((tag, members))
    return render(request, 'members/tags.html', {'tags': tags})


@login_required
@user_passes_test(is_active_member, login_url='member_not_active')
def tag_cloud(request):
    tags = []
    for tag in UserProfile.tags.all().order_by('name'):
        member_count = User.helper.members_with_tag(tag).count()
        if member_count:
            tags.append((tag, member_count))
    return render(request, 'members/tag_cloud.html', {'tags': tags})

@login_required
@user_passes_test(is_active_member, login_url='member_not_active')
def org_tag_cloud(request):
    tags=[]
    # org_count = 1
    for tag in Organization.tags.all().order_by('name'):
        org_count = Organization.helper.organizations_with_tag(tag).count()
        tags.append((tag, org_count))
    return render(request, 'members/tag_cloud.html', {'tags': tags})

@login_required
@user_passes_test(is_active_member, login_url='member_not_active')
def tag(request, tag):
    members = User.helper.members_with_tag(tag)
    context = {'tag': tag, 'members': members, 'settings': settings}
    return render(request, 'members/tag.html', context)


@login_required
def user_tags(request, username):
    user = get_object_or_404(User, username=username)
    if not user == request.user:
        if not request.user.is_staff:
            return HttpResponseRedirect(reverse('member_profile', kwargs={'username': request.user.username}))
    user_tags = user.profile.tags.all()

    error = None
    if request.method == 'POST':
        tag = request.POST.get('tag')
        if tag:
            for p in string.punctuation:
                if p in tag:
                    error = "Tags can't contain punctuation."
                    break
            else:
                user.profile.tags.add(tag.lower())
        return HttpResponseRedirect(reverse('member_profile', kwargs={'username': user.username}))

    all_tags = UserProfile.tags.all()
    context = {'user': user, 'user_tags': user_tags, 'all_tags': all_tags,
        'error': error, 'settings': settings}
    return render(request, 'members/user_tags.html', context)

# @login_required
# def delete_tag(request, username, tag):
#     user = get_object_or_404(User, username=username)
#     if not user == request.user:
#         if not request.user.is_staff:
#             # If not this user and not staff, send this person back to their profile
#             return HttpResponseRedirect(reverse('member_profile', kwargs={'username': request.user.username}))
#     user.profile.tags.remove(tag)
#     return HttpResponseRedirect(reverse('member_user_tags', kwargs={'username': username}))

@login_required
def delete_tag_in_profile(request, username, tag):
    user = get_object_or_404(User, username=username)
    if not user == request.user:
        if not request.user.is_staff:
            # If not this user and not staff, send this person back to their profile
            return HttpResponseRedirect(reverse('member_profile', kwargs={'username': request.user.username}))
    user.profile.tags.remove(tag)
    return HttpResponseRedirect(reverse('member_profile', kwargs={'username': username}))

# Copyright 2016 Office Nomads LLC (http://www.officenomads.com/) Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the License. You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0 Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the specific language governing permissions and limitations under the License.
