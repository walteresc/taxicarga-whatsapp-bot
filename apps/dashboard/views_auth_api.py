from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt, csrf_protect, ensure_csrf_cookie
import json
import logging

logger = logging.getLogger(__name__)


@csrf_exempt
@ensure_csrf_cookie
@require_http_methods(["POST"])
def api_login(request):
    """API login endpoint - accepts JSON with username/password, returns user info"""
    try:
        data = json.loads(request.body)
        username = data.get('username', '')
        password = data.get('password', '')

        if not username or not password:
            return JsonResponse({'error': 'Username and password required'}, status=400)

        logger.warning(f"[AUTH_API] Login attempt: username={username}")
        user = authenticate(request, username=username, password=password)
        logger.warning(f"[AUTH_API] authenticate() returned: {user}")
        if user is None:
            logger.warning(f"[AUTH_API] Login FAILED for {username}")
            return JsonResponse({'error': 'Invalid credentials'}, status=401)

        # Log the user in
        login(request, user)

        # Return user info
        return JsonResponse({
            'status': 'ok',
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'full_name': user.get_full_name() or user.username,
                'is_staff': user.is_staff,
                'is_superuser': user.is_superuser,
            }
        })
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["GET"])
@login_required
def api_user(request):
    """Get current user info"""
    user = request.user
    return JsonResponse({
        'status': 'ok',
        'user': {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'full_name': user.get_full_name() or user.username,
            'is_staff': user.is_staff,
            'is_superuser': user.is_superuser,
        }
    })


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def api_logout(request):
    """Logout endpoint - CSRF exempt for API consistency with login"""
    logger.warning(f"[AUTH_API] Logout attempt: user={request.user.username}")
    logout(request)
    logger.warning(f"[AUTH_API] Logout complete, authenticated={request.user.is_authenticated}")
    return JsonResponse({'status': 'ok'})


@ensure_csrf_cookie
@require_http_methods(["GET"])
def api_check_auth(request):
    """Check if user is authenticated"""
    if request.user.is_authenticated:
        return JsonResponse({
            'authenticated': True,
            'user': {
                'id': request.user.id,
                'username': request.user.username,
                'full_name': request.user.get_full_name() or request.user.username,
            }
        })
    return JsonResponse({'authenticated': False})
